#!/usr/bin/env python3
"""
📥 수신 폴더 점검 (읽기 전용) / inbox check, read-only.

처리된 녹음은 '완료' 폴더로 옮겨지므로, 수신 폴더(DRIVE_FOLDER_ID)에 남은 녹음은 대개
'처리 안 됨'(늦게 올라옴·처리 실패) 아니면 '처리됐는데 옮기기 실패'다. 이 스크립트는
  ① 수신 폴더의 녹음을 처리 기록(docs/processed.txt)과 맞춰 보고,
  ② 강사 기록(docs/carrot)은 있는데 복습 페이지가 없는 날마다 그 날짜 녹음이 어디 있는지,
  ③ 하루에 녹음이 여러 개로 나뉜 날(연결이 끊겨 다시 건 수업)을 보여 준다.
아무것도 옮기거나 고치지 않는다. Actions 로그는 공개이므로 파일명·날짜·크기만 찍는다
(파일명 형식은 이미 docs/processed.txt 에 공개돼 있다).

실행: GitHub → Actions → "🗄️ 원본 보관 점검" (이 단계가 함께 돈다)
"""
import base64
import collections
import glob
import json
import os
import re
from datetime import datetime, timedelta, timezone

from google.oauth2 import service_account
from googleapiclient.discovery import build

KST = timezone(timedelta(hours=9))
MB_PER_MIN = 0.93  # 실측: 18.6MB ≈ 1,202초 녹음
_STAMP = re.compile(r"(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(\d{2})(\d{2})(\d{2})")


def stamp(name):
    """파일명 → (YYYY-MM-DD, HH:MM:SS). 못 읽으면 ('', '')."""
    m = _STAMP.search(name or "")
    if not m:
        return "", ""
    y, mo, d, h, mi, s = m.groups()
    return f"{y}-{mo}-{d}", f"{h}:{mi}:{s}"


def list_audio(service, folder):
    """폴더 안의 녹음 전부 (여러 쪽 넘김 포함)."""
    files, token = [], None
    while True:
        r = service.files().list(
            q=(f"'{folder}' in parents and trashed = false "
               "and (mimeType contains 'audio/' or mimeType contains 'video/mp4')"),
            pageSize=1000, pageToken=token,
            fields="nextPageToken, files(id, name, size, createdTime)",
        ).execute()
        files += r.get("files", [])
        token = r.get("nextPageToken")
        if not token:
            return files


def processed_keys(path="docs/processed.txt"):
    ids, names = set(), set()
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            fid, _, name = line.strip().partition("|")
            if fid:
                ids.add(fid.strip())
            if name.strip():
                names.add(name.strip())
    return ids, names


def describe(f):
    day, t = stamp(f["name"])
    mb = int(f.get("size") or 0) / 1e6
    up = datetime.fromisoformat(f["createdTime"].replace("Z", "+00:00")).astimezone(KST)
    return f"{day} {t} · {mb:.1f}MB(약 {mb / MB_PER_MIN:.0f}분) · 올라온 시각 {up:%m-%d %H:%M} · {f['name']}"


def main():
    creds_b64 = os.environ.get("GOOGLE_CREDENTIALS", "")
    inbox = os.environ.get("DRIVE_FOLDER_ID", "").strip()
    done = os.environ.get("DRIVE_DONE_FOLDER_ID", "").strip()
    if not creds_b64 or not inbox:
        print("❌ 설정 누락: GOOGLE_CREDENTIALS 또는 DRIVE_FOLDER_ID")
        return 0
    creds = service_account.Credentials.from_service_account_info(
        json.loads(base64.b64decode(creds_b64)),
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    ids, names = processed_keys()

    # ① 수신 폴더
    in_files = sorted(list_audio(service, inbox), key=lambda f: f["name"])
    todo = [f for f in in_files if f["id"] not in ids and f["name"] not in names]
    copies = len(in_files) - len(todo)
    nostamp = sum(1 for f in in_files if not stamp(f["name"])[0])
    # 처리된 녹음은 완료 폴더로 옮겨지는데, 폰 동기화 앱(FolderSync)이 '사라진' 파일을 다시 올려
    # 같은 이름의 사본이 수신 폴더에 쌓인다(새 ID). 본 흐름은 파일명으로 걸러내므로 해는 없다.
    print(f"📥 수신 폴더 녹음 {len(in_files)}개 — 처리 안 됨 {len(todo)} · 이미 처리된 수업의 사본 {copies}"
          + (f" · 파일명에 날짜가 없는 녹음 {nostamp}개(이름은 공개 로그라 생략)" if nostamp else ""))
    for f in todo:
        print(f"   🔴 처리 안 됨: {describe(f)}")

    # ② 강사 기록은 있는데 페이지가 없는 날 → 그 날짜 녹음이 어디 있나
    done_files = list_audio(service, done) if done else []
    by_day = collections.defaultdict(list)
    for where, fs in (("수신", in_files), ("완료", done_files)):
        for f in fs:
            by_day[stamp(f["name"])[0]].append((where, f))
    carrot = set()
    for p in glob.glob("docs/carrot/2026-*.json"):
        carrot |= {x.get("createDate", "")[:10] for x in json.load(open(p, encoding="utf-8"))["data"]["list"]}
    pages = {os.path.basename(p)[:10] for p in glob.glob("docs/20*.html")}
    missing = sorted(d for d in carrot - pages if d)
    print(f"\n📚 강사 기록은 있는데 복습 페이지가 없는 날 {len(missing)}일")
    counts = collections.Counter()
    for d in missing:
        hits = by_day.get(d, [])
        if not hits:
            counts["녹음 없음"] += 1
            print(f"   {d}: 녹음 없음 (수신·완료 폴더 모두)")
            continue
        for where, f in hits:
            key = f"{where} 폴더에 있음"
            counts[key] += 1
            print(f"   {d}: {where} 폴더 · {describe(f)}")
    print("   → " + " · ".join(f"{k} {v}" for k, v in counts.items()))

    # ③ 하루에 녹음이 여러 개인 날 (연결이 끊겨 나뉜 수업)
    multi = {d: v for d, v in by_day.items() if d and len(v) > 1}
    print(f"\n✂️ 녹음이 2개 이상인 날 {len(multi)}일")
    for d in sorted(multi):
        parts = sorted(multi[d], key=lambda wf: wf[1]["name"])
        print(f"   {d}: " + " | ".join(f"{stamp(f['name'])[1]} {int(f.get('size') or 0) / 1e6 / MB_PER_MIN:.0f}분({w})"
                                      for w, f in parts))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:  # noqa: BLE001 — 점검용이라 실패해도 다른 단계에 영향 없게
        print(f"⚠️ 수신 폴더 점검 실패: {type(e).__name__}: {str(e)[:200]}")

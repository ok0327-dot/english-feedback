#!/usr/bin/env python3
"""
🗄️ Whisper 원본 보관 파일 점검 / raw-transcript archive check.

Drive '완료' 폴더의 보관 파일(whisper_raw.jsonl)이 준비됐는지, 서비스 계정이 실제로 내용을 고쳐 쓸 수
있는지 확인한다. 쓰기 확인은 **같은 내용을 그대로 다시 올리는 것**이라 기록은 바뀌지 않는다.
Confirms the archive file exists and that the service account can really update it (by re-uploading
identical bytes, so nothing changes).

배경: 서비스 계정은 Drive 에 새 파일을 만들 수 없다(저장 용량 0) — 그래서 사용자가 만든 파일에 덧붙인다.
종료 코드: 0=준비 완료 / 1=파일 없음 또는 쓰기 불가 / 2=설정 누락
실행: GitHub → Actions → "🗄️ 원본 보관 점검" → Run workflow
"""
import base64
import io
import json
import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

FILE_NAME = os.environ.get("DRIVE_RAW_FILE_NAME", "").strip() or "whisper_raw.jsonl"


def explain_missing(service, folder):
    """
    못 찾았을 때 흔한 원인(다른 폴더에 올림 · 메모장이 .txt 를 붙임 · 이름 오타)을 짚어 준다.
    Actions 로그는 공개이므로 폴더 ID 는 찍지 않고 '완료 폴더 / 수신 폴더 / 다른 폴더' 로만 말한다.
    """
    inbox = os.environ.get("DRIVE_FOLDER_ID", "").strip()
    try:
        name = service.files().get(fileId=folder, fields="name").execute().get("name")
        print(f"   ℹ️ 완료 폴더 이름: '{name}' (처리 끝난 녹음 전화영어_….m4a 가 옮겨지는 곳)")
    except Exception as e:  # noqa: BLE001 — 안내용이라 실패해도 점검 결과는 그대로
        print(f"   ⚠️ 완료 폴더 정보를 읽지 못함: {type(e).__name__}")
    stem = FILE_NAME.split("_")[0]  # 'whisper' — 이름 앞부분으로 넓게 찾는다(Drive 의 contains 는 앞부분 일치)
    try:
        near = service.files().list(
            q=f"name contains '{stem}' and trashed = false",
            pageSize=10,
            fields="files(name, mimeType, parents, createdTime)",
        ).execute().get("files", [])
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠️ 비슷한 파일 찾기 실패: {type(e).__name__}")
        return
    if not near:
        print(f"   ℹ️ 로봇 계정이 볼 수 있는 곳에 이름이 '{stem}' 으로 시작하는 파일이 없습니다 → "
              "로봇과 공유되지 않은 폴더에 올렸거나, PC 의 Drive 앱 동기화가 아직 안 끝났을 수 있습니다")
    for f in near:
        parents = f.get("parents") or []
        where = "완료 폴더" if folder in parents else "수신 폴더(녹음이 처음 올라오는 곳)" if inbox and inbox in parents else "다른 폴더"
        print(f"   🔎 비슷한 파일: {f['name']!r} · {where} · 형식 {f.get('mimeType')} · 올린 시각 {f.get('createdTime', '')[:16]}Z")
    if near:
        print(f"   👉 이름을 정확히 '{FILE_NAME}' 로, 위치를 완료 폴더로 맞추면 됩니다")


def main():
    creds_b64 = os.environ.get("GOOGLE_CREDENTIALS", "")
    folder = os.environ.get("DRIVE_RAW_FOLDER_ID", "").strip() or os.environ.get("DRIVE_DONE_FOLDER_ID", "").strip()
    if not creds_b64 or not folder:
        print("❌ 설정 누락: GOOGLE_CREDENTIALS 또는 폴더 ID(DRIVE_DONE_FOLDER_ID) 없음")
        return 2
    creds = service_account.Credentials.from_service_account_info(
        json.loads(base64.b64decode(creds_b64)),
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    found = service.files().list(
        q=f"name = '{FILE_NAME}' and '{folder}' in parents and trashed = false",
        pageSize=5,
        fields="files(id, size, ownedByMe, capabilities(canEdit))",
    ).execute().get("files", [])
    if not found:
        print(f"❌ '{FILE_NAME}' 파일이 완료 폴더에 없습니다. 빈 파일을 만들어 올려 주세요.")
        explain_missing(service, folder)
        return 1
    if len(found) > 1:
        # 본 흐름(process_lesson.read_raw_archive)은 이 상태에서 아무 데도 쓰지 않는다
        print(f"❌ 같은 이름의 파일이 {len(found)}개입니다. 어느 쪽에도 기록하지 않으니 하나만 남기세요.")
        return 1
    f = found[0]
    print(f"✅ 파일 발견: 크기 {f.get('size')} bytes · 서비스 계정 소유={f.get('ownedByMe')} · "
          f"편집 가능={f.get('capabilities', {}).get('canEdit')}")

    content = service.files().get_media(fileId=f["id"]).execute() or b""
    if f.get("size") is not None and int(f["size"]) != len(content):
        print("❌ 내용을 끝까지 받지 못했습니다 (크기 불일치). 다시 실행해 보세요.")
        return 1
    lines = [ln for ln in content.decode("utf-8", errors="replace").splitlines() if ln.strip()]
    last = ""
    if lines:
        try:
            last = json.loads(lines[-1]).get("lesson_date", "")
        except ValueError:
            last = "(마지막 줄이 JSON 이 아님)"
    print(f"📚 보관된 수업 {len(lines)}건" + (f" · 마지막 수업일 {last}" if last else ""))

    try:
        service.files().update(
            fileId=f["id"],
            media_body=MediaIoBaseUpload(io.BytesIO(content), mimetype="application/x-ndjson", resumable=False),
            fields="id",
        ).execute()
    except Exception as e:
        print(f"❌ 쓰기 불가: {type(e).__name__}: {str(e)[:400]}")
        return 1
    print("✅ 쓰기 확인 완료 (같은 내용을 다시 올림 — 기록 변화 없음). 다음 수업부터 자동으로 쌓입니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

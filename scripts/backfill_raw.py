#!/usr/bin/env python3
"""
🗄️ 빠진 Whisper 원본 채우기 / backfill missing raw transcripts.

처리 기록(docs/processed.txt)에는 있는데 Drive 보관 파일(whisper_raw.jsonl)에는 없는 수업을 찾아,
'완료' 폴더의 녹음을 다시 받아쓰고(Groq Whisper) 보관 파일에 덧붙인다.
Finds lessons that were processed but have no line in the archive, re-transcribes them and appends.

왜 필요한가: 원본 보관(process_lesson.py 9단계)은 처리 기록을 남긴 '뒤에' 돈다. 그날 보관이 실패하면
그 녹음은 이미 '처리 완료'라 다음 실행이 다시 집지 않는다 → 이 스크립트가 매일 빈자리를 메운다.
비유: 송장 사본을 서랍에 못 넣은 날이 있으면, 다음 날 배송 대장과 서랍을 맞춰 보고 빠진 것만 다시 복사해 넣는 것.

- 최근 수업부터 최대 --max 건 (기본 2). 녹음이 Drive 에 없는 수업은 건수에 세지 않는다.
- --since 이후 수업만 (기본 RAW_BACKFILL_SINCE, 없으면 2026-10-05 = 원본 보관을 시작하기로 한 날). all = 전체.
- Groq 한도(429)에 걸리면 그 자리에서 멈춘다 — 다음 실행이 이어서 채운다.
- --dry-run: 빠진 목록과 녹음 존재 여부만 보여 주고, 받아쓰거나 쓰지 않는다.
- 다시 받아쓴 줄에는 "backfill": true 가 붙는다 (그날 실제로 쓰인 전사와 조금 다를 수 있다).
- 로그에 전사 내용은 찍지 않는다 (공개 저장소의 Actions 로그는 누구나 본다).
- 종료 코드는 항상 0 (best-effort). 보관 파일 준비 상태 확인은 scripts/check_raw_archive.py 가 맡는다.

실행 / run:  python3 scripts/backfill_raw.py [--max N] [--since YYYY-MM-DD|all] [--dry-run]
"""
import argparse
import contextlib
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)  # PROCESSED_FILE 이 상대 경로라 저장소 루트에서 돈다
# 메일 설정은 여기서 안 쓰지만 import 때 필수로 읽힌다 → 더미로 채워 메일 비밀번호를 이 단계에 주지 않는다
for _k in ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.setdefault(_k, "unused")
import process_lesson as P  # noqa: E402

DEFAULT_SINCE = os.environ.get("RAW_BACKFILL_SINCE", "").strip() or "2026-10-05"


def _lesson_day(filename):
    """파일명 → 'YYYY-MM-DD' (본 흐름과 같은 규칙). 알 수 없으면 ''."""
    with contextlib.redirect_stdout(io.StringIO()):  # extract_lesson_date 의 안내 출력은 숨긴다
        d = P.extract_lesson_date(filename)
    return d.strftime("%Y-%m-%d") if d else ""


def processed_lessons(path=None):
    """처리 기록 → [(파일 ID, 파일명, 수업일)]. 파일명 없는 옛 줄(ID만)은 날짜를 몰라 뺀다."""
    path = path or P.PROCESSED_FILE
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            if "|" not in line:
                continue
            file_id, filename = (x.strip() for x in line.split("|", 1))
            day = _lesson_day(filename)
            if file_id and day:
                out.append((file_id, filename, day))
    return out


def archived_keys(content):
    """보관 파일 내용 → (이미 적힌 파일 ID 집합, 파일명 집합). 깨진 줄은 무시."""
    ids, names = set(), set()
    for line in content.decode("utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            ids.add(rec.get("drive_file_id") or "")
            names.add(rec.get("source_file") or "")
    return ids - {""}, names - {""}


def _recording_state(service, file_id):
    """녹음이 Drive 에 있는지: 'ok' / 'gone'(지워짐·휴지통) / 'error'(그 밖의 접속 오류)."""
    try:
        meta = service.files().get(fileId=file_id, fields="id, trashed").execute()
    except Exception as e:  # noqa: BLE001
        status = getattr(getattr(e, "resp", None), "status", None)
        return "gone" if str(status) == "404" else "error"
    return "gone" if meta.get("trashed") else "ok"


def run(max_items=2, since=DEFAULT_SINCE, dry_run=False, processed_path=None,
        service_factory=None, download=None, transcribe=None):
    """빠진 원본을 채운다. 결과 요약 dict 반환 (테스트에서 검사)."""
    summary = {"missing": 0, "saved": 0, "gone": 0, "failed": 0, "stopped": ""}
    if not P.SAVE_RAW:
        print("ℹ️ SAVE_RAW=0 → 원본 채우기 건너뜀")
        summary["stopped"] = "disabled"
        return summary

    service = (service_factory or (lambda: P.get_drive_service(readonly=False)))()
    status, _, content = P.read_raw_archive(service)
    if status != "ok" and not (dry_run and status == "no_file"):
        print(f"ℹ️ 보관 파일 상태 '{status}' → 원본 채우기 건너뜀 (점검: Actions → 🗄️ 원본 보관 점검)")
        summary["stopped"] = status
        return summary
    have_ids, have_names = archived_keys(content)

    # 같은 녹음이 새 ID 로 다시 올라온 경우(FolderSync)까지 막으려고 파일명도 본다
    todo, seen = [], set(have_names)
    for file_id, name, day in sorted(processed_lessons(processed_path), key=lambda x: x[2], reverse=True):
        if since and day < since:
            continue
        if file_id in have_ids or name in seen:
            continue
        seen.add(name)
        todo.append((file_id, name, day))
    summary["missing"] = len(todo)
    print(f"🗄️ 보관된 수업 {len(have_ids)}건 · {since or '전체'} 이후 빠진 수업 {len(todo)}건"
          + (" (보관 파일 아직 없음)" if status == "no_file" else ""))

    attempts = 0
    for file_id, name, day in todo:
        if not dry_run and attempts >= max_items:
            break
        state = _recording_state(service, file_id)
        if dry_run:
            print(f"   - {day} {name} · 녹음 {'있음' if state == 'ok' else '없음' if state == 'gone' else '확인 실패'}")
            continue
        if state != "ok":
            summary["gone" if state == "gone" else "failed"] += 1
            print(f"   ⏭️ {day} 녹음을 열 수 없어 건너뜀 ({state})")
            continue

        attempts += 1
        path = None
        try:
            path = (download or P.download_recording)(service, file_id, name)
            text, duration, segments = (transcribe or P.transcribe_audio)(path)
            if not (text or "").strip():
                summary["failed"] += 1
                print(f"   ⚠️ {day} 전사 결과가 비어 있어 건너뜀")
                continue
            with contextlib.redirect_stdout(io.StringIO()):
                lesson_date = P.extract_lesson_date(name)
            record = P._build_raw_record(name, file_id, lesson_date, text, duration, segments, backfill=True)
            result = P._append_raw_record(service, record)
        except Exception as e:  # noqa: BLE001 — 한 건 실패가 전체를 멈추지 않게
            if "(429)" in str(e):
                summary["stopped"] = "rate_limit"
                print("⏸️ Groq 한도(429) → 여기서 멈춤. 다음 실행이 이어서 채운다")
                break
            summary["failed"] += 1
            print(f"   ⚠️ {day} 실패 (치명적이지 않음): {type(e).__name__}: {str(e)[:200]}")
            continue
        finally:
            if path and os.path.exists(path):
                os.remove(path)

        if result in ("saved", "duplicate"):
            summary["saved"] += result == "saved"
            print(f"   🗄️ {day} 원본 채움 ({duration:.0f}초)" if result == "saved" else f"   ℹ️ {day} 이미 있음")
        else:  # 보관 파일 자체가 문제(사라짐·중복·덜 받음) → 더 쓰지 않는다
            summary["stopped"] = result
            print(f"   ⚠️ 보관 파일 상태 '{result}' → 원본 채우기 중단")
            break

    if not dry_run:
        print(f"✅ 원본 채우기 끝: 채움 {summary['saved']} · 녹음 없음 {summary['gone']} · 실패 {summary['failed']}"
              + (f" · 남은 것 다음 실행으로 ({summary['stopped'] or '건수 제한'})"
                 if summary["saved"] + summary["gone"] + summary["failed"] < summary["missing"] else ""))
    return summary


def main():
    ap = argparse.ArgumentParser(description="빠진 Whisper 원본을 Drive 보관 파일에 채운다")
    ap.add_argument("--max", type=int, default=2, help="한 번에 다시 받아쓸 최대 건수 (기본 2)")
    ap.add_argument("--since", default=DEFAULT_SINCE, help="이 날짜(YYYY-MM-DD) 이후 수업만. all = 전체")
    ap.add_argument("--dry-run", action="store_true", help="목록만 보여 주고 아무것도 쓰지 않음")
    a = ap.parse_args()
    since = "" if a.since.strip().lower() in ("", "all") else a.since.strip()
    try:
        run(max_items=max(a.max, 0), since=since, dry_run=a.dry_run)
    except Exception as e:  # noqa: BLE001 — best-effort: 본 흐름(이미 끝남)에 영향 주지 않게 항상 0
        print(f"⚠️ 원본 채우기 실패 (치명적이지 않음): {type(e).__name__}: {str(e)[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

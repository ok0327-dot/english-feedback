#!/usr/bin/env python3
"""
Whisper 원본 보관(save_raw_transcript) 안전성 검사 / safety tests for the raw-transcript archive step.

핵심은 "어떤 실패도 본 흐름을 깨지 않는다"이다. 가짜 Drive 로 성공·예외·무응답·파일 없음을 재현한다.
실행 / run:  python3 tests/test_raw_archive.py   (pytest 불필요, 네트워크 미사용)
"""
import json
import os
import sys
import time
from datetime import datetime

# process_lesson 은 불러올 때 필수 환경변수를 읽으므로 가짜 값을 먼저 넣는다
for key in ("GOOGLE_CREDENTIALS", "GROQ_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.setdefault(key, "x")
os.environ["DRIVE_DONE_FOLDER_ID"] = "DONE_FOLDER"
os.environ.pop("DRIVE_RAW_FOLDER_ID", None)
os.environ.pop("SAVE_RAW", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import process_lesson as pl  # noqa: E402


class _Call:
    def __init__(self, fn):
        self._fn = fn

    def execute(self):
        return self._fn()


class _NotFound(Exception):
    """googleapiclient HttpError 404 흉내 (resp.status 만 본다)."""
    resp = type("Resp", (), {"status": 404})()


class FakeDrive:
    """보관 파일 하나를 흉내 내는 가짜 Drive / a fake Drive holding one archive file."""

    def __init__(self, content=b"", exists=True, fail_on=None, hang_on=None, wrong_size=False,
                 dupes=False, recordings=None):
        self.content, self.exists = content, exists
        self.fail_on, self.hang_on, self.wrong_size = fail_on, hang_on, wrong_size
        self.dupes = dupes
        self.recordings = recordings or {}  # 녹음 파일 ID → "ok" / "trashed" (없으면 404)
        self.updates = 0
        self.last_query = ""

    def files(self):
        return self

    def _step(self, name, fn):
        def run():
            if self.hang_on == name:
                time.sleep(5)
            if self.fail_on == name:
                raise RuntimeError(f"boom:{name}")
            return fn()
        return _Call(run)

    def list(self, q="", **_):
        self.last_query = q
        size = len(self.content) + (7 if self.wrong_size else 0)
        files = [{"id": "ARCHIVE", "size": str(size)}] if self.exists else []
        if self.exists and self.dupes:
            files.append({"id": "ARCHIVE2", "size": "0"})
        return self._step("list", lambda: {"files": files})

    def get(self, fileId=None, **_):
        def run():
            if fileId not in self.recordings:
                raise _NotFound()
            return {"id": fileId, "trashed": self.recordings[fileId] == "trashed"}
        return _Call(run)

    def get_media(self, fileId=None):
        return self._step("get", lambda: self.content)

    def update(self, fileId=None, media_body=None, **_):
        def apply():
            fd = media_body.stream()
            fd.seek(0)
            self.content = fd.read()
            self.updates += 1
            return {"id": fileId}
        return self._step("update", apply)


SEGMENTS = [
    {"id": 0, "start": 0.0, "end": 2.5, "text": " Hello Joey.", "avg_logprob": -0.2,
     "no_speech_prob": 0.01, "compression_ratio": 1.1, "tokens": [1, 2, 3], "seek": 0, "temperature": 0.0},
    {"id": 1, "start": 3.1, "end": 6.0, "text": " I go to Sapporo last week.", "avg_logprob": -0.4,
     "no_speech_prob": 0.02, "compression_ratio": 1.2, "tokens": [4, 5], "seek": 0, "temperature": 0.0},
]


def save(drive, file_id="AUDIO1", timeout=2):
    return pl.save_raw_transcript(
        "전화영어_025180304_20261006080041.m4a", file_id, datetime(2026, 10, 6),
        "Hello Joey. I go to Sapporo last week.", 5.9, SEGMENTS,
        timeout=timeout, service_factory=lambda: drive,
    )


def _name(day):
    return f"전화영어_025180304_{day.replace('-', '')}080020.m4a"


def backfill_checks(check):
    """빠진 원본 채우기(scripts/backfill_raw.py) — 처리 기록과 보관 파일을 맞춰 빠진 것만 채운다."""
    import tempfile
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import backfill_raw as B

    tmp = tempfile.mkdtemp()
    processed = os.path.join(tmp, "processed.txt")
    with open(processed, "w", encoding="utf-8") as f:
        f.write("OLDID\n")                                  # 파일명 없는 옛 줄 → 날짜 모름 → 제외
        for fid, day in (("A", "2026-10-28"), ("B", "2026-10-27"), ("C", "2026-10-26"),
                         ("E", "2026-10-21"), ("D", "2026-10-02")):
            f.write(f"{fid}|{_name(day)}\n")
    archived_a = (json.dumps({"schema": 1, "drive_file_id": "A", "source_file": _name("2026-10-28")}) + "\n").encode()
    all_ok = {k: "ok" for k in "ABCDE"}

    calls = []

    def download(service, fid, name):
        path = os.path.join(tmp, f"{fid}.m4a")
        open(path, "wb").write(b"audio")
        calls.append(("dl", fid))
        return path

    def transcribe_ok(path):
        calls.append(("tr", os.path.basename(path)))
        return "Hello Joey.", 1200.0, SEGMENTS

    def run(drive, transcribe=transcribe_ok, **kw):
        calls.clear()
        kw.setdefault("since", "2026-10-05")
        return B.run(processed_path=processed, service_factory=lambda: drive,
                     download=download, transcribe=transcribe, **kw)

    # B1) 최근 것부터 최대 2건, 이미 있는 A·기간 밖 D·옛 줄은 건드리지 않음
    d = FakeDrive(content=archived_a, recordings=dict(all_ok))
    s = run(d, max_items=2)
    recs = [json.loads(x) for x in d.content.decode().splitlines()]
    check("채우기: 최근 2건(B,C)만", s["saved"] == 2 and [r["drive_file_id"] for r in recs] == ["A", "B", "C"])
    check("채우기: backfill 표시·날짜", recs[1].get("backfill") is True and recs[1]["lesson_date"] == "2026-10-27")
    check("채우기: 빠진 수 = B,C,E", s["missing"] == 3)
    check("채우기: 받은 녹음 지움", not any(n.endswith(".m4a") for n in os.listdir(tmp)))

    # B2) 다시 돌리면 남은 E 만
    s = run(d, max_items=5)
    check("채우기: 재실행 시 남은 것만", s["saved"] == 1 and s["missing"] == 1 and calls == [("dl", "E"), ("tr", "E.m4a")])

    # B3) 녹음이 지워진 수업은 건수에 안 셈
    rec = dict(all_ok)
    rec.pop("B")
    d = FakeDrive(content=archived_a, recordings=rec)
    s = run(d, max_items=1)
    check("채우기: 지워진 녹음 건너뛰고 다음 것", s["gone"] == 1 and s["saved"] == 1 and ("dl", "C") in calls)

    # B4) Groq 한도(429) → 그 자리에서 멈춤
    def transcribe_429(path):
        calls.append(("tr", path))
        raise Exception('Groq API 오류 (429): {"error":"rate_limit_exceeded"}')
    d = FakeDrive(content=archived_a, recordings=dict(all_ok))
    s = run(d, transcribe=transcribe_429, max_items=5)
    check("채우기: 429 에서 멈춤", s["stopped"] == "rate_limit" and len([c for c in calls if c[0] == "tr"]) == 1
          and d.updates == 0)

    # B5) 한 건 실패해도 다음 건 진행
    def transcribe_flaky(path):
        if path.endswith("B.m4a"):
            raise RuntimeError("timeout")
        return transcribe_ok(path)
    d = FakeDrive(content=archived_a, recordings=dict(all_ok))
    s = run(d, transcribe=transcribe_flaky, max_items=2)
    check("채우기: 한 건 실패 후 계속", s["failed"] == 1 and s["saved"] == 1)

    # B6) 목록만 보기: 보관 파일이 아직 없어도 동작, 아무것도 받거나 쓰지 않음
    d = FakeDrive(exists=False, recordings=dict(all_ok))
    s = run(d, dry_run=True)
    check("채우기: dry-run 무변경", s["missing"] == 4 and calls == [] and d.updates == 0)

    # B7) 보관 파일 없음(실제 실행) → 받아쓰지 않고 멈춤
    s = run(FakeDrive(exists=False, recordings=dict(all_ok)), max_items=2)
    check("채우기: 보관 파일 없으면 중단", s["stopped"] == "no_file" and calls == [])

    # B8) 같은 녹음이 새 ID 로 올라온 경우 → 파일명으로 중복 판단
    archived_b_other_id = archived_a + (json.dumps({"drive_file_id": "B-old", "source_file": _name("2026-10-27")})
                                        + "\n").encode()
    d = FakeDrive(content=archived_b_other_id, recordings=dict(all_ok))
    s = run(d, dry_run=True)
    check("채우기: 파일명 중복 제외", s["missing"] == 2)

    # B9) since=all(빈 값) → 기간 밖 D 도 포함
    s = run(FakeDrive(content=archived_a, recordings=dict(all_ok)), dry_run=True, since="")
    check("채우기: 전체 기간", s["missing"] == 4)

    # B10) 끄는 스위치
    pl.SAVE_RAW = False
    s = run(FakeDrive(content=archived_a, recordings=dict(all_ok)), max_items=2)
    pl.SAVE_RAW = True
    check("채우기: SAVE_RAW=0 이면 미실행", s["stopped"] == "disabled" and calls == [])


def main():
    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    # 1) 성공: 기존 줄 보존 + 새 줄 추가, 덩치 큰 항목(tokens)은 빠짐
    old = b'{"schema": 1, "drive_file_id": "OLD"}\n'
    d = FakeDrive(content=old)
    check("saved 반환", save(d) == "saved")
    lines = d.content.decode("utf-8").splitlines()
    check("기존 줄 보존", d.content.startswith(old) and len(lines) == 2)
    rec = json.loads(lines[1])
    check("원문·날짜·파일 ID 기록", rec["text"].startswith("Hello Joey") and rec["lesson_date"] == "2026-10-06"
          and rec["drive_file_id"] == "AUDIO1")
    check("세그먼트 시각·신뢰도 유지, tokens 제거",
          rec["segments"][1]["start"] == 3.1 and "avg_logprob" in rec["segments"][0] and "tokens" not in rec["segments"][0])
    check("완료 폴더에서 이름으로 찾음", "DONE_FOLDER" in d.last_query and "whisper_raw.jsonl" in d.last_query)

    # 2) 줄바꿈 없이 끝난 기존 파일에도 줄이 붙지 않음
    d = FakeDrive(content=b'{"drive_file_id": "OLD"}')
    save(d)
    check("줄바꿈 보정", len(d.content.decode("utf-8").splitlines()) == 2)

    # 3) 빈 파일(처음 올린 상태)
    d = FakeDrive(content=b"")
    check("빈 파일에 첫 줄", save(d) == "saved" and len(d.content.decode("utf-8").splitlines()) == 1)

    # 4) 같은 녹음 재실행 → 중복 기록 안 함
    check("중복 방지", save(d) == "duplicate" and d.updates == 1)

    # 5) 보관 파일 없음 → 조용히 건너뜀
    d = FakeDrive(exists=False)
    check("파일 없음 건너뜀", save(d) == "no_file" and d.updates == 0)

    # 6) 덜 받은 경우(크기 불일치) → 덮어쓰지 않음
    d = FakeDrive(content=old, wrong_size=True)
    check("크기 불일치 시 덮어쓰기 금지", save(d) == "size_mismatch" and d.content == old)

    # 7) 단계별 예외 → 밖으로 새지 않음, 기존 내용 그대로
    for step in ("list", "get", "update"):
        d = FakeDrive(content=old, fail_on=step)
        try:
            status = save(d)
        except BaseException as e:  # noqa: BLE001 — 예외가 새면 그 자체가 실패
            status = f"RAISED {e!r}"
        check(f"{step} 예외 흡수", status == "error" and d.content == old)

    # 8) 접속 자체 실패(자격증명 오류 등)
    def broken_factory():
        raise RuntimeError("no credentials")
    status = pl.save_raw_transcript("a.m4a", "X", None, "t", 1, [], timeout=2, service_factory=broken_factory)
    check("접속 실패 흡수", status == "error")

    # 9) 무응답 → 시간 제한 안에 돌아옴
    d = FakeDrive(content=old, hang_on="get")
    t0 = time.time()
    status = save(d, timeout=1)
    check("무응답 시 시간 제한", status == "timeout" and time.time() - t0 < 3)

    # 10) 끄는 스위치
    pl.SAVE_RAW = False
    d = FakeDrive(content=old)
    check("SAVE_RAW=0 이면 미실행", save(d) == "disabled" and d.updates == 0)
    pl.SAVE_RAW = True

    # 11) 이상한 입력(세그먼트 None·문자열 섞임)에도 죽지 않음
    d = FakeDrive(content=b"")
    status = pl.save_raw_transcript("a.m4a", "Y", None, "t", 0, [None, "x", {"id": 0, "text": "ok"}],
                                    timeout=2, service_factory=lambda: d)
    check("이상한 세그먼트 입력", status == "saved" and json.loads(d.content)["segments"] == [{"id": 0, "text": "ok"}])

    # 12) 같은 이름 보관 파일이 2개 → 어느 쪽에도 쓰지 않음
    d = FakeDrive(content=old, dupes=True)
    check("중복 보관 파일이면 쓰지 않음", save(d) == "ambiguous" and d.updates == 0)

    backfill_checks(check)

    print(f"\n{'ALL PASS' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

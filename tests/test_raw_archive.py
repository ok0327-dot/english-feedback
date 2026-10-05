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


class FakeDrive:
    """보관 파일 하나를 흉내 내는 가짜 Drive / a fake Drive holding one archive file."""

    def __init__(self, content=b"", exists=True, fail_on=None, hang_on=None, wrong_size=False):
        self.content, self.exists = content, exists
        self.fail_on, self.hang_on, self.wrong_size = fail_on, hang_on, wrong_size
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
        return self._step("list", lambda: {"files": [{"id": "ARCHIVE", "size": str(size)}] if self.exists else []})

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

    print(f"\n{'ALL PASS' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

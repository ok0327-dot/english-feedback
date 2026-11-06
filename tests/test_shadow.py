#!/usr/bin/env python3
"""
그림자 실행 검사 / tests for scripts/shadow_feedback.py — 가짜 Claude·가짜 보관 파일 (네트워크·토큰 미사용).
실행 / run:  python3 tests/test_shadow.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile
from datetime import datetime

for key in ("GOOGLE_CREDENTIALS", "GROQ_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.setdefault(key, "x")
os.environ["DIAG_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shadow_feedback as S  # noqa: E402

pl = S.pl
SECRET_RAW = "I go to Sapporo last week with my friend zxqv"  # 로그에 찍히면 안 되는 원본 문장


def name(stamp):
    return f"전화영어_025180304_{stamp}.m4a"


def main():
    failures = []

    def check(label, cond):
        print(("PASS " if cond else "FAIL ") + label)
        if not cond:
            failures.append(label)

    repo, shadow = tempfile.mkdtemp(), tempfile.mkdtemp()
    os.makedirs(os.path.join(repo, "docs"))
    for slug, stamp in (("2026-11-05", "20261105080000"), ("2026-11-06", "20261106080016"), ("2026-10-01", "20261001080000")):
        open(os.path.join(repo, "docs", f"{slug}.html"), "w", encoding="utf-8").write(f"<span>🎙 {name(stamp)}</span>")
    open(os.path.join(repo, "docs", "metadata.json"), "w").write(json.dumps({"2026-11-05": {"target_grammar": "Articles"}}))
    os.makedirs(os.path.join(shadow, "shadow"))
    open(os.path.join(shadow, "shadow", "2026-11-05.json"), "w").write("{}")  # 이미 만든 수업
    os.chdir(repo)

    # 1) 할 일: 최근 3일 · 그림자판 없는 것만
    todo = S.pending(shadow, 3, today=datetime(2026, 11, 7, tzinfo=pl.KST))
    check("할 일: 11/06 만 (11/05 는 이미 있음, 10/01 은 범위 밖)", todo == [("2026-11-06", name("20261106080016"))])

    # 2) 나뉜 녹음 묶기 — 페이지의 첫 녹음이 든 수업 전체
    records = [
        {"source_file": name("20261106080016"), "duration": 33.0, "text": "Hello Joey.", "segments": [{"start": 0.0, "end": 2.0}]},
        {"source_file": name("20261106080106"), "duration": 1200.0, "text": SECRET_RAW, "segments": [{"start": 1.0, "end": 4.0}]},
        {"source_file": name("20261106090000"), "duration": 1200.0, "text": "other lesson", "segments": []},
    ]
    parts = S.lesson_parts(name("20261106080016"), records)
    check("묶기: 33초 조각 + 본편, 다른 수업 제외", [p["source_file"][-18:-4] for p in parts] == ["20261106080016", "20261106080106"])

    # 3) 4단계를 차례로, 앞 결과를 다음 입력으로
    content = "\n".join(json.dumps(r, ensure_ascii=False) for r in records).encode()
    pl.read_raw_archive = lambda service: ("ok", "ARCH", content)
    calls = []

    def fake_claude(prompt):
        calls.append(prompt)
        n = len(calls)
        out = {1: "[Tutor] Hello Joey.\n[Student] " + SECRET_RAW, 2: "[Tutor] Hello Joey.\n[Student] " + SECRET_RAW + " (verified)",
               3: "## 피드백 초안", 4: "## 최종 피드백\n- ❌ 학습자 원문 (As Said): I go to Sapporo"}[n]
        return out, {"model": "claude-opus-5-5", "in": 100, "cache_write": 10, "cache_read": 0, "out": 50, "seconds": 1}

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = S.run(shadow, days=3, service="svc", runner=fake_claude)
    check("실행: 1건 완료", r == {"done": 1, "failed": 0})
    check("1단계: 원본 + 개선 지시문", SECRET_RAW in calls[0] and "고치지 마세요" in calls[0]
          and "영문법 실수가 있는 쪽이 [Student]" not in calls[0])
    check("2단계: 1단계 결과를 검증", "[Student] " + SECRET_RAW in calls[1] and "실수 여부로 판단 금지" in calls[1])
    check("3단계: 검증 결과로 피드백 (main 과 같은 지시문)", "(verified)" in calls[2])
    check("4단계: 초안 검토", "## 피드백 초안" in calls[3] and "(verified)" in calls[3])
    out = json.load(open(os.path.join(shadow, "shadow", "2026-11-06.json"), encoding="utf-8"))
    check("결과: 최종 피드백·녹음 2개·지시문 지문 4개", out["feedback"].startswith("## 최종 피드백")
          and len(out["recordings"]) == 2 and len(out["steps"]) == 4 and out["duration"] == 1233.0)
    html = open(os.path.join(shadow, "docs-shadow", "2026-11-06.html"), encoding="utf-8").read()
    check("페이지: 그림자판 표시", "🌗 그림자판" in html)
    runs = [json.loads(x) for x in open(os.path.join(shadow, "shadow", "runs.jsonl"), encoding="utf-8")]
    check("기록: done · 토큰 합계", runs[-1]["status"] == "done" and runs[-1]["out"] == 200)
    check("로그에 원본·피드백 내용 없음", SECRET_RAW not in buf.getvalue() and "Sapporo" not in buf.getvalue())
    check("원본 전사는 어디에도 저장 안 함", not any(SECRET_RAW in open(os.path.join(dp, f), encoding="utf-8", errors="ignore").read()
                                         and f.endswith(".jsonl") for dp, _, fs in os.walk(shadow) for f in fs))

    # 4) 다시 돌리면 건너뜀 (중복 0)
    with contextlib.redirect_stdout(io.StringIO()):
        r = S.run(shadow, days=3, service="svc", runner=fake_claude)
    check("중복 없음: 다시 돌리면 할 일 0", r == {"done": 0, "failed": 0} and len(calls) == 4)

    # 5) 실패 — 기록만, 반쯤 만든 결과는 남기지 않음, 다음 실행이 다시 시도
    os.remove(os.path.join(shadow, "shadow", "2026-11-06.json"))
    os.remove(os.path.join(shadow, "docs-shadow", "2026-11-06.html"))

    def broken(prompt):
        if "## 피드백" in prompt or len(calls) > 5:
            raise RuntimeError("claude 오류: rate limited")
        calls.append(prompt)
        return "x", {"in": 1, "out": 1}
    with contextlib.redirect_stdout(io.StringIO()):
        r = S.run(shadow, days=3, service="svc", runner=broken)
    runs = [json.loads(x) for x in open(os.path.join(shadow, "shadow", "runs.jsonl"), encoding="utf-8")]
    check("실패: 기록되고 결과 파일 없음(다음에 다시)", r["failed"] == 1 and runs[-1]["status"] == "failed"
          and not os.path.exists(os.path.join(shadow, "shadow", "2026-11-06.json")))

    # 6) 원본이 아직 없으면 건너뜀
    pl.read_raw_archive = lambda service: ("ok", "ARCH", b"")
    with contextlib.redirect_stdout(io.StringIO()):
        S.run(shadow, days=3, service="svc", runner=fake_claude)
    runs = [json.loads(x) for x in open(os.path.join(shadow, "shadow", "runs.jsonl"), encoding="utf-8")]
    check("원본 없음: no_raw 기록", runs[-1]["status"] == "no_raw")

    print(f"\n{'ALL PASS' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

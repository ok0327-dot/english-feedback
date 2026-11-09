#!/usr/bin/env python3
"""
주 엔진 승격 검사 / tests for the Claude-first engine + plain-grammar prompts (가짜 Claude·Gemini — 네트워크·토큰 미사용).
- Claude 가 되면 Claude, 실패하면 그 실행 내내 Gemini 사다리 (본 흐름 보호)
- LLM_ENGINE=gemini 면 Claude 를 아예 안 부른다 (끄는 스위치)
- claude_request: CLI 의 JSON 해석 · 오류 시 전사 내용을 메시지에 싣지 않음
- 보정·화자 지시문은 개선판이 기본 · 피드백·검토 지시문에 '쉬운 말' 규칙
실행 / run:  python3 tests/test_engine.py
"""
import contextlib
import io
import json
import os
import subprocess
import sys

for key in ("GOOGLE_CREDENTIALS", "GROQ_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.setdefault(key, "x")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import process_lesson as pl  # noqa: E402

SECRET = "I go to Sapporo last week zxqv"  # 오류 메시지·로그에 실리면 안 되는 학생 문장


def main():
    failures = []

    def check(label, cond):
        print(("PASS " if cond else "FAIL ") + label)
        if not cond:
            failures.append(label)

    calls = {"claude": 0, "gemini": 0}

    def fake_claude_ok(prompt, system_msg=None, timeout=None):
        calls["claude"] += 1
        return "CLAUDE:" + prompt[:5], {"model": "claude-opus-5-5", "in": 10, "out": 5, "seconds": 1}

    def fake_claude_bad(prompt, system_msg=None, timeout=None):
        calls["claude"] += 1
        raise subprocess.TimeoutExpired("claude", 480)

    def fake_gemini(prompt, *a, model=None, **k):
        calls["gemini"] += 1
        return "GEMINI:" + model

    real_claude_request = pl.claude_request
    pl.gemini_request = fake_gemini
    pl.shutil.which = lambda name: "/usr/bin/claude"

    def reset(engine, claude_fn):
        calls.update(claude=0, gemini=0)
        pl.LLM_ENGINE, pl._CLAUDE_DOWN, pl.claude_request = engine, None, claude_fn
        pl._CLAUDE_SPENT = 0.0
        pl.LLM_TRACE.clear()

    quiet = contextlib.redirect_stdout(io.StringIO())

    # 1) Claude 가 되면 Claude 만
    reset("claude", fake_claude_ok)
    with quiet:
        r = pl.llm_request("hello world")
    check("Claude 성공 → Claude 결과, Gemini 안 부름", r == "CLAUDE:hello" and calls == {"claude": 1, "gemini": 0})
    check("기록: 엔진·사용량", pl.LLM_TRACE and pl.LLM_TRACE[0][0] == "claude" and pl.LLM_TRACE[0][1]["out"] == 5)

    # 2) Claude 가 실패하면 Gemini 로, 그 뒤로는 Claude 를 다시 부르지 않음 (시간 낭비 방지)
    reset("claude", fake_claude_bad)
    with quiet:
        r1 = pl.llm_request("first")
        r2 = pl.llm_request("second")
    check("Claude 실패(시간 초과) → Gemini 1순위 결과", r1 == "GEMINI:" + pl.GEMINI_MODELS[0])
    check("한 번 실패하면 그 실행의 나머지는 바로 Gemini", calls == {"claude": 1, "gemini": 2} and r2.startswith("GEMINI:"))
    check("기록: Gemini 모델명", [e for e, _ in pl.LLM_TRACE] == [pl.GEMINI_MODELS[0]] * 2)

    # 3) 끄는 스위치 · claude 명령이 없을 때
    reset("gemini", fake_claude_ok)
    with quiet:
        pl.llm_request("x")
    check("LLM_ENGINE=gemini → Claude 안 부름", calls == {"claude": 0, "gemini": 1})
    reset("claude", fake_claude_ok)
    pl.shutil.which = lambda name: None
    with quiet:
        pl.llm_request("x")
    check("claude 명령 미설치 → Gemini", calls == {"claude": 0, "gemini": 1})
    pl.shutil.which = lambda name: "/usr/bin/claude"

    # 3.5) 실행 전체 시간 예산 (코덱스 리뷰): 호출마다 남은 예산만큼만 기다리고, 1분도 안 남으면 Gemini
    timeouts = []

    def fake_claude_slow(prompt, system_msg=None, timeout=None):
        timeouts.append(timeout)
        calls["claude"] += 1
        pl._CLAUDE_SPENT += 500  # 느리지만 성공한 호출 흉내 (실제 경과 시간에 더해진다)
        return "CLAUDE", {"model": "m", "in": 1, "out": 1, "seconds": 500}
    reset("claude", fake_claude_slow)
    with quiet:
        pl.llm_request("a")
        pl.llm_request("b")
        pl.llm_request("c")
        r3 = pl.llm_request("d")
    check("예산: 첫 호출은 480초 제한, 다음은 남은 예산(700→200초)",
          [round(t) for t in timeouts[:3]] == [pl.CLAUDE_TIMEOUT, min(pl.CLAUDE_TIMEOUT, pl.CLAUDE_BUDGET - 500), pl.CLAUDE_BUDGET - 1000])
    check("예산: 1분 미만 남으면 Gemini 로 (4번째)", calls == {"claude": 3, "gemini": 1} and r3.startswith("GEMINI:")
          and "예산" in (pl._CLAUDE_DOWN or ""))

    # 4) claude_request — CLI JSON 해석 (진짜 함수, 가짜 subprocess)
    real_run = pl.subprocess.run
    seen = {}

    def fake_run(cmd, input=None, **k):
        seen["cmd"], seen["input"] = cmd, input
        out = json.dumps({"result": "OK", "usage": {"input_tokens": 3, "cache_creation_input_tokens": 100,
                                                   "cache_read_input_tokens": 7, "output_tokens": 9},
                          "modelUsage": {"claude-opus-5-5": {}}})
        return subprocess.CompletedProcess(cmd, 0, out, "")
    pl.subprocess.run = fake_run
    text, usage = real_claude_request("PROMPT " + SECRET, system_msg="COACH RULES")
    check("claude_request: 본문·입력 토큰 합산(캐시 포함)·출력", text == "OK" and usage["in"] == 110 and usage["out"] == 9)
    check("claude_request: 도구 끔 · 지시문은 표준입력으로 · 역할 지시문 합침",
          seen["cmd"][:4] == ["claude", "-p", "--tools", ""] and SECRET in seen["input"]
          and SECRET not in " ".join(seen["cmd"]) and "COACH RULES" in seen["cmd"][-1])

    def fake_run_err(cmd, input=None, **k):
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"is_error": True, "subtype": "error_during_execution",
                                                               "result": "echo " + SECRET}), "")
    pl.subprocess.run = fake_run_err
    try:
        real_claude_request(SECRET)
        msg = ""
    except RuntimeError as e:
        msg = str(e)
    check("claude_request: 오류는 예외 · 메시지에 학생 문장 없음 (공개 로그)", msg.startswith("claude 오류") and SECRET not in msg)
    pl.subprocess.run = lambda cmd, input=None, **k: subprocess.CompletedProcess(cmd, 1, "not json", "boom")
    try:
        real_claude_request("x")
        ok = False
    except RuntimeError as e:
        ok = "해석 실패" in str(e)
    check("claude_request: JSON 아님 → 예외", ok)
    pl.subprocess.run = real_run

    # 5) 지시문 — 개선판 기본 · 쉬운 말 규칙
    got = []
    pl.llm_request = lambda prompt, *a, system_msg=None, **k: got.append((prompt, system_msg)) or "x"
    with quiet:
        pl.clean_transcript("RAW", [{"start": 0, "end": 1, "text": "hi"}])
        pl.verify_speaker_labels("T")
        pl.generate_feedback("T", recent_categories=["articles"])
        pl.review_feedback("T", "F")
    clean_p, verify_p = got[0][0], got[1][0]
    check("보정: 학생 말 고치지 않기 · '실수 있는 쪽 = 학생' 규칙 없음",
          "고치지 마세요" in clean_p and "영문법 실수가 있는 쪽이 [Student]" not in clean_p
          and "문맥상 맞지 않는 단어를 올바른 단어로 수정" not in clean_p)
    check("화자 검증: 실수 여부로 판단 금지", "실수 여부로 판단 금지" in verify_p and "영어 실력 일관성" not in verify_p)
    fb_prompt, fb_sys = got[2]
    check("피드백: 쉬운 말 규칙이 역할 지시문에", pl.PLAIN_GRAMMAR_RULE in fb_sys and "과거분사" in fb_sys)
    check("피드백: Category 줄 유지 + 🎯 오늘의 패턴 줄", "`Category: <영어 카테고리 라벨>`" in fb_prompt and "🎯 오늘의 패턴" in fb_prompt)
    check("검토: 쉬운 말 점검 + Category 보존", pl.PLAIN_GRAMMAR_RULE in got[3][0] and "Category: ...` 라인은 **반드시 그대로 보존**" in got[3][0])

    # 6) 집계 호환 — 🎯 줄이 붙어도 Category 라벨만 뽑힌다
    fb = "**3. 🔧 고질적 문법 '한 놈만 패기'**\n\n**Category: subject-verb agreement**\n🎯 오늘의 패턴: 그 사람 하나면 끝에 s\n"
    check("메타데이터: Category 라벨만", pl.extract_metadata(fb)["target_grammar"] == "subject-verb agreement")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import build_weekly_review as W
    check("주간 집계: Category 라벨만", W.grammar_label(" Category: subject-verb agreement\n🎯 오늘의 패턴: 끝에 s") == "subject-verb agreement")

    print(f"\n{'✅ 모두 통과' if not failures else '❌ 실패 ' + str(len(failures)) + '건'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

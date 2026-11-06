#!/usr/bin/env python3
"""
Gemini 429 처리 검사 — 하루 한도면 기다리지 않고 바로 다음 모델, 분당 한도면 기존처럼 재시도.
실행 / run:  python3 tests/test_gemini_quota.py   (네트워크 미사용)
"""
import os
import sys

for key in ("GOOGLE_CREDENTIALS", "GROQ_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.setdefault(key, "x")
os.environ["GEMINI_API_KEY"] = "fake"
os.environ.pop("GEMINI_MODELS", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import process_lesson as pl  # noqa: E402


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, str(body)

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def quota(qid):
    return {"error": {"code": 429, "message": "You exceeded your current quota", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": qid}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "30s"},
    ]}}


def main():
    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    check("하루 한도 판별", pl._is_daily_quota(Resp(429, quota("GenerateRequestsPerDayPerProjectPerModel-FreeTier"))))
    check("분당 한도는 하루 한도 아님", not pl._is_daily_quota(Resp(429, quota("GenerateRequestsPerMinutePerProjectPerModel-FreeTier"))))
    check("본문이 JSON 이 아니면 아님", not pl._is_daily_quota(Resp(429, ValueError("not json"))))
    check("details 없으면 아님", not pl._is_daily_quota(Resp(429, {"error": {"code": 429}})))

    # gemini_request: 하루 한도면 sleep 없이 바로 예외, 분당 한도면 재시도(sleep) 후 성공
    sleeps, calls = [], []
    pl.time.sleep = lambda s: sleeps.append(s)
    seq = []
    pl.requests.post = lambda *a, **k: (calls.append(1), seq.pop(0))[1]
    seq[:] = [Resp(429, quota("GenerateRequestsPerDayPerProjectPerModel-FreeTier"))]
    try:
        pl.gemini_request("x", model="gemini-2.5-flash")
        check("하루 한도: 바로 실패", False)
    except Exception as e:
        check("하루 한도: 바로 실패(대기 없음)", "하루 무료 한도" in str(e) and sleeps == [] and len(calls) == 1)

    sleeps.clear(), calls.clear()
    ok = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "OK"}]}}]}
    seq[:] = [Resp(429, quota("GenerateRequestsPerMinutePerProjectPerModel-FreeTier")), Resp(200, ok)]
    check("분당 한도: 기다렸다 재시도해 성공", pl.gemini_request("x", model="gemini-2.5-flash") == "OK" and sleeps == [30])

    sleeps.clear(), calls.clear()
    seq[:] = [Resp(429, {"error": {"code": 429}})] * 4 + [Resp(200, ok)]
    try:
        pl.gemini_request("x", model="gemini-2.5-flash")
        check("읽을 수 없는 429: 두 번만 기다리고 다음 모델로", False)
    except Exception as e:
        check("읽을 수 없는 429: 두 번만 기다리고 다음 모델로", "재시도 2회 초과" in str(e) and sleeps == [30, 60])

    # llm_request: 2.5-flash 하루 한도 → 3.5-flash 로 넘어감
    tried = []

    def fake(prompt, *a, model=None, **k):
        tried.append(model)
        if model == "gemini-2.5-flash":
            raise Exception("Gemini 하루 무료 한도 소진 [gemini-2.5-flash] → 다음 모델로")
        return "fine"
    pl.gemini_request = fake
    check("기본 사다리 순서", pl.GEMINI_MODELS == ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-2.5-flash-lite"])
    check("한도 소진 시 3.5-flash 로", pl.llm_request("x") == "fine" and tried == ["gemini-2.5-flash", "gemini-3.5-flash"])

    print(f"\n{'ALL PASS' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

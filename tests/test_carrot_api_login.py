#!/usr/bin/env python3
"""
당근 API 우선 로그인 · 예비 경로 · 달 완결성 검사 / tests for API-first login, fallback and month completeness.

배경: 2026-09~11 정기 수집 실패 6건이 전부 '화면에서 다음을 눌러도 비밀번호 칸이 안 나옴' 이었다.
그래서 화면 대신 사이트가 내부적으로 부르는 로그인 API 를 먼저 쓰고, 화면 로그인은 예비로만 둔다.
응답 모양은 2026-11-15 실측값을 그대로 흉내 낸다:
  · 없는 계정 로그인 → HTTP 200 {"success":false,"code":0,"message":"This account is not valid.","data":false}
  · 무효 토큰으로 allFeedback → HTTP 200 {"success":false,"code":500,...}
실행 / run:  python3 tests/test_carrot_api_login.py   (pytest 불필요, 네트워크 미사용)
"""
import json
import os
import shutil
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import fetch_carrot_feedback as F  # noqa: E402
import build_carrot_page as B  # noqa: E402

EMAIL, PASSWORD = "me@example.com", "s3cret-pw"
failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


class Resp:
    def __init__(self, status=200, body=None, raw=None):
        self.status_code = status
        self._body, self._raw = body, raw

    def json(self):
        if self._raw is not None:
            raise ValueError("not json")
        return self._body


class Patch:
    """모듈 속성을 잠깐 바꿨다가 되돌린다 / temporarily replace module attributes."""

    def __init__(self, obj, **attrs):
        self.obj, self.attrs, self.old = obj, attrs, {}

    def __enter__(self):
        for k, v in self.attrs.items():
            self.old[k] = getattr(self.obj, k)
            setattr(self.obj, k, v)
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            setattr(self.obj, k, v)


def raises(fn, exc):
    try:
        fn()
    except exc as e:
        return e
    except Exception as e:  # noqa: BLE001
        return f"WRONG {type(e).__name__}: {e}"
    return None


def month_body(ym, n, day0=1):
    items = [{"idxFeedback": i, "createDate": f"{ym}-{day0 + i:02d} 08:00:00", "memo": "m", "subList": []}
             for i in range(n)]
    return {"success": True, "data": {"list": items}}


def fake_get_factory(counts, calls=None, stray_for=None):
    """searchYM 에 맞춰 달 자료를 돌려주는 가짜 GET / fake GET keyed by searchYM."""
    def fake_get(url, headers=None, timeout=None):
        ym = url.split("searchYM=")[-1]
        if calls is not None:
            calls.append(ym)
        if headers.get("accesstoken") not in ("tok", "btok"):
            return Resp(200, {"success": False, "code": 500, "message": "Illegal base64 character 2d"})
        if stray_for == ym:
            return Resp(200, month_body("2026-11", 3))  # 서버가 searchYM 을 무시한 상황 / ignored searchYM
        return Resp(200, month_body(ym, counts.get(ym, 0)))
    return fake_get


# ───────────────────────────── api_login ─────────────────────────────
def test_api_login():
    def post(resp):
        return lambda *a, **k: resp

    ok = Resp(200, {"success": True, "data": {"accessToken": "tok", "isAgree": "Y"}})
    with Patch(F.requests, post=post(ok)):
        check("API 로그인 성공 → accessToken", F.api_login(EMAIL, PASSWORD) == "tok")

    rej = Resp(200, {"success": False, "code": 0, "message": f"This account is not valid. ({EMAIL})", "data": False})
    with Patch(F.requests, post=post(rej)):
        e = raises(lambda: F.api_login(EMAIL, PASSWORD), F.CredentialsRejected)
        check("success=false → CredentialsRejected", isinstance(e, F.CredentialsRejected))
        check("거절 메시지에 서버 문구는 남고 이메일은 가려짐",
              isinstance(e, F.CredentialsRejected) and "not valid" in str(e) and EMAIL not in str(e))
        check("CredentialsRejected 는 LoginError 가 아님(재시도 경로가 못 잡음)",
              not issubclass(F.CredentialsRejected, F.LoginError))

    with Patch(F.requests, post=post(Resp(401, {}))):
        check("HTTP 401 → CredentialsRejected", isinstance(raises(lambda: F.api_login(EMAIL, PASSWORD), F.CredentialsRejected), F.CredentialsRejected))
    for status in (403, 404, 500, 503):
        with Patch(F.requests, post=post(Resp(status, {}))):
            check(f"HTTP {status} → LoginError(예비 경로)", isinstance(raises(lambda: F.api_login(EMAIL, PASSWORD), F.LoginError), F.LoginError))
    with Patch(F.requests, post=post(Resp(200, raw="<html>"))):
        check("JSON 아님 → LoginError", isinstance(raises(lambda: F.api_login(EMAIL, PASSWORD), F.LoginError), F.LoginError))
    with Patch(F.requests, post=post(Resp(200, {"success": True, "data": {}}))):
        check("토큰 없음 → LoginError", isinstance(raises(lambda: F.api_login(EMAIL, PASSWORD), F.LoginError), F.LoginError))
    with Patch(F.requests, post=post(Resp(200, ["x"]))):
        check("응답이 dict 아님 → LoginError", isinstance(raises(lambda: F.api_login(EMAIL, PASSWORD), F.LoginError), F.LoginError))

    def boom(*a, **k):
        raise F.requests.ConnectionError("down")
    with Patch(F.requests, post=boom):
        check("연결 실패 → LoginError", isinstance(raises(lambda: F.api_login(EMAIL, PASSWORD), F.LoginError), F.LoginError))


# ───────────────────────────── get_token ─────────────────────────────
def test_get_token():
    browser_calls = []

    def browser_ok(email, password):
        browser_calls.append(1)
        return "btok"

    def browser_fail(email, password):
        browser_calls.append(1)
        raise F.LoginError("playwright 미설치 / not installed")

    def api_fail(email, password):
        raise F.LoginError("로그인 API HTTP 503")

    def api_reject(email, password):
        raise F.CredentialsRejected("rejected")

    cur = lambda: ("2026-11", "2026-10")  # noqa: E731
    get_ok = fake_get_factory({"2026-11": 3})

    with Patch(F, current_and_previous_month=cur, api_login=lambda e, p: "tok", login_and_get_token=browser_ok), \
            Patch(F.requests, get=get_ok):
        browser_calls.clear()
        check("API 성공 → ('tok','api') 이고 브라우저 안 씀",
              F.get_token(EMAIL, PASSWORD) == ("tok", "api") and not browser_calls)

    with Patch(F, current_and_previous_month=cur, api_login=api_fail, login_and_get_token=browser_ok), \
            Patch(F.requests, get=get_ok):
        browser_calls.clear()
        check("API 실패 → 브라우저 1회 → ('btok','browser')",
              F.get_token(EMAIL, PASSWORD) == ("btok", "browser") and len(browser_calls) == 1)

    with Patch(F, current_and_previous_month=cur, api_login=lambda e, p: "bad-token", login_and_get_token=browser_ok), \
            Patch(F.requests, get=get_ok):
        browser_calls.clear()
        check("API 토큰을 수집 API 가 거절 → 브라우저로", F.get_token(EMAIL, PASSWORD) == ("btok", "browser"))

    with Patch(F, current_and_previous_month=cur, api_login=api_reject, login_and_get_token=browser_ok), \
            Patch(F.requests, get=get_ok):
        browser_calls.clear()
        e = raises(lambda: F.get_token(EMAIL, PASSWORD), F.CredentialsRejected)
        check("서버 거절 → 그대로 올라가고 브라우저로 비밀번호 재전송 안 함",
              isinstance(e, F.CredentialsRejected) and not browser_calls)

    with Patch(F, current_and_previous_month=cur, api_login=api_fail, login_and_get_token=browser_fail), \
            Patch(F.requests, get=get_ok):
        e = raises(lambda: F.get_token(EMAIL, PASSWORD), F.LoginError)
        check("둘 다 실패 → 두 원인을 함께 보고(브라우저 오류가 API 원인을 안 가림)",
              isinstance(e, F.LoginError) and "HTTP 503" in str(e) and "playwright" in str(e))


# ───────────────────────────── fetch_month ─────────────────────────────
def test_fetch_month():
    calls = []
    with Patch(F.requests, get=fake_get_factory({"2026-06": 2}, calls, stray_for="2026-06")), Patch(F.time, sleep=lambda s: None):
        e = raises(lambda: F.fetch_month("tok", "2026-06"), F.ApiError)
        check("다른 달 자료가 오면 ApiError(덮어쓰기 전 차단) · 재시도 안 함",
              isinstance(e, F.ApiError) and "2026-06" in str(e) and calls == ["2026-06"])
    with Patch(F.requests, get=fake_get_factory({})):
        check("무효 토큰(200·success=false) → ApiError", isinstance(raises(lambda: F.fetch_month("nope", "2026-11"), F.ApiError), F.ApiError))
        check("빈 달(success=true·빈 목록)은 정상", F.fetch_month("tok", "2026-08")["success"] is True)


# ───────────────────────────── 달 완결성 / month completeness ─────────────────────────────
def test_completeness():
    check("6월은 7/8 부터 완결", str(F.month_final_date("2026-06")) == "2026-07-08")
    check("12월은 다음 해 1/8 부터 완결", str(F.month_final_date("2026-12")) == "2027-01-08")
    check("06-26 에 받은 6월 = 미완결(실제 사례)", not F.is_final("2026-06", {"2026-06": "2026-06-26"}))
    check("기준일 당일에 받으면 완결", F.is_final("2026-06", {"2026-06": "2026-07-08"}))
    check("기록 없음·깨진 값 = 미완결", not F.is_final("2026-06", {}) and not F.is_final("2026-06", {"2026-06": "x"}))

    args = types.SimpleNamespace(months=[], backfill=True, since="2026-02")
    have = {f"2026-{m:02d}" for m in range(2, 12)}
    with Patch(F, current_and_previous_month=lambda: ("2026-11", "2026-10")):
        allm = F.plan_months(args, have=have, fetched_on={})
        check("기록 없으면 2~11월 전부 1회 재수집", allm == sorted(have, reverse=True))
        fo = {ym: "2026-11-09" for ym in have}
        fo["2026-06"] = "2026-06-26"
        check("완결 기록이 있으면 6월(덜 받은 달)+이번·지난 달만",
              F.plan_months(args, have=have, fetched_on=fo) == ["2026-11", "2026-10", "2026-06"])
        check("빠진 달(파일 없음)은 여전히 채움",
              "2026-03" in F.plan_months(args, have=have - {"2026-03"}, fetched_on=fo))
        args2 = types.SimpleNamespace(months=[], backfill=False, since="2026-02")
        check("백필 아닌 기본 실행은 이번·지난 달 그대로", F.plan_months(args2) == ["2026-11", "2026-10"])


# ───────────────────────────── main() 전체 경로 / end-to-end paths ─────────────────────────────
def run_main(argv, api_login, browser, counts, seed=None, meta=None):
    tmp = tempfile.mkdtemp()
    carrot, debug = os.path.join(tmp, "carrot"), os.path.join(tmp, "debug")
    os.makedirs(carrot)
    for ym, n in (seed or {}).items():
        with open(os.path.join(carrot, f"{ym}.json"), "w", encoding="utf-8") as f:
            json.dump(month_body(ym, n), f)
    if meta is not None:
        with open(os.path.join(carrot, "_meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f)
    os.environ["CARROT_EMAIL"], os.environ["CARROT_PASSWORD"] = EMAIL, PASSWORD
    with Patch(F, CARROT=carrot, DEBUG_DIR=debug, api_login=api_login, login_and_get_token=browser,
               current_and_previous_month=lambda: ("2026-11", "2026-10")), \
            Patch(F.requests, get=fake_get_factory(counts)), Patch(F.time, sleep=lambda s: None):
        code = F.main(argv)
    return code, tmp, carrot, debug


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_main():
    browser_calls = []

    def browser(e, p):
        browser_calls.append(1)
        return "btok"

    def api_reject(e, p):
        raise F.CredentialsRejected(F._short(f"rejected for {EMAIL}/{PASSWORD}", [EMAIL, PASSWORD]))

    # ① API 경로 + 덜 받은 6월 다시 받기(20 → 22일) / API path refreshes the partial June
    code, tmp, carrot, _ = run_main(["--backfill"], lambda e, p: "tok", browser,
                                    {"2026-06": 22, "2026-11": 6, "2026-10": 19},
                                    seed={"2026-06": 20, "2026-10": 19, "2026-11": 6},
                                    meta={"fetched_at": "2026-11-09", "months": ["2026-11", "2026-10"],
                                          "fetched_on": {"2026-06": "2026-06-26", "2026-10": "2026-11-09",
                                                         "2026-11": "2026-11-09"}})
    meta = read_json(os.path.join(carrot, "_meta.json"))
    check("API 경로 exit 0 · 브라우저 안 씀", code == 0 and not browser_calls)
    check("6월 20 → 22일로 갱신", F.month_day_count(os.path.join(carrot, "2026-06.json")) == 22)
    check("_meta: login_via=api · fetched_on 갱신 · 기존 fetched_at/months 키 유지",
          meta.get("login_via") == "api" and meta["fetched_on"]["2026-06"] == meta["fetched_at"]
          and "months" in meta and "2026-06" in meta["months"])
    with Patch(B, CARROT=carrot):
        fa, src, est = B.read_freshness()
        check("페이지 생성기가 새 _meta 를 그대로 읽음(신선도·수집 월)",
              fa == meta["fetched_at"] and src == "_meta.json" and not est and "2026-06" in B.fetched_months())
    shutil.rmtree(tmp)

    # ② 다시 받았더니 일수가 줄면 기존 파일 유지 / never shrink an existing month
    code, tmp, carrot, _ = run_main(["2026-06"], lambda e, p: "tok", browser, {"2026-06": 18, "2026-11": 6},
                                    seed={"2026-06": 20})
    check("일수 감소(20→18) → 기존 파일 유지 · exit 0",
          code == 0 and F.month_day_count(os.path.join(carrot, "2026-06.json")) == 20)
    shutil.rmtree(tmp)

    # ③ 서버 거절 → exit 5 · 브라우저 안 씀 · 알림용 이유에 비밀번호 없음
    browser_calls.clear()
    code, tmp, _, debug = run_main(["2026-11"], api_reject, browser, {"2026-11": 6})
    reason = open(os.path.join(debug, "reason.txt"), encoding="utf-8").read()
    check("서버 거절 → exit 5 · 브라우저 재시도 없음", code == F.EXIT_REJECTED == 5 and not browser_calls)
    check("reason.txt 에 이메일·비밀번호 원문 없음", PASSWORD not in reason and EMAIL not in reason and "rejected" in reason)
    shutil.rmtree(tmp)

    # ④ API·브라우저 모두 실패 → exit 3 · 두 원인 모두 알림 이유에
    def api_fail(e, p):
        raise F.LoginError("로그인 API HTTP 503")

    def browser_fail(e, p):
        raise F.LoginError("chromium 실행 실패")
    code, tmp, _, debug = run_main(["2026-11"], api_fail, browser_fail, {"2026-11": 6})
    reason = open(os.path.join(debug, "reason.txt"), encoding="utf-8").read()
    check("둘 다 실패 → exit 3 · 이유에 두 원인", code == 3 and "503" in reason and "chromium" in reason)
    shutil.rmtree(tmp)

    # ⑤ API 실패 → 브라우저로 성공 → login_via=browser 기록
    browser_calls.clear()
    code, tmp, carrot, _ = run_main(["2026-11"], api_fail, browser, {"2026-11": 6})
    check("예비 경로 성공 → exit 0 · login_via=browser",
          code == 0 and len(browser_calls) == 1 and read_json(os.path.join(carrot, "_meta.json"))["login_via"] == "browser")
    shutil.rmtree(tmp)


def main():
    test_api_login()
    test_get_token()
    test_fetch_month()
    test_completeness()
    test_main()
    print(f"\n{'ALL PASS' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

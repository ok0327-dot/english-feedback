#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🥕 Carrot English 강사 공식 피드백 수집기 / fetcher.

이메일+비밀번호로 로그인(Playwright headless) → 앱이 보내는 요청의 accesstoken
헤더를 가로채 → 그 토큰으로 allFeedback API를 월별 호출 → docs/carrot/YYYY-MM.json 저장.
(저장소 토큰 스캐닝이 아니라 '앱 자신의 요청 헤더'를 캡처하는 방식.)

자격증명은 환경변수로만 받는다(절대 하드코딩/커밋 금지):
  CARROT_EMAIL, CARROT_PASSWORD

CLI:
  python3 scripts/fetch_carrot_feedback.py            # 이번 달 + 지난 달
  python3 scripts/fetch_carrot_feedback.py 2026-06    # 특정 월(들)
의존성: pip install playwright requests 후 python -m playwright install chromium
"""
import os, sys, json, datetime, time
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARROT = os.path.join(ROOT, "docs", "carrot")
KST = datetime.timezone(datetime.timedelta(hours=9))

LOGIN_URL = "https://carrotfarm.carrotenglish.com/auth/startEmail"
FEEDBACK_PAGE = "https://carrotfarm.carrotenglish.com/myClassroom/feedback?idxLecture=0"
API = "https://homeapi.carrotenglish.com/app/myclass/allFeedback?searchYM={ym}"


def target_months(args):
    if args:
        return args
    today = datetime.datetime.now(KST).date()
    cur = today.strftime("%Y-%m")
    first = today.replace(day=1)
    prev = (first - datetime.timedelta(days=1)).strftime("%Y-%m")
    return [cur, prev]


def login_and_get_token(email, password):
    """Playwright로 로그인하고, 앱이 보내는 allFeedback 요청의 accesstoken 헤더를 캡처."""
    from playwright.sync_api import sync_playwright
    captured = {"token": None}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context().new_page()

        def on_request(req):
            if "allFeedback" in req.url:
                tok = req.headers.get("accesstoken")
                if tok:
                    captured["token"] = tok
        page.on("request", on_request)

        page.goto(LOGIN_URL, wait_until="networkidle")
        page.get_by_placeholder("이메일을 입력해주세요").fill(email)
        page.get_by_text("다음").click()
        page.get_by_placeholder("비밀번호를 입력해주세요").fill(password)
        page.get_by_text("로그인 하기").click()
        page.wait_for_url("**/myClassroom**", timeout=20000)

        # 피드백 페이지를 열어 앱이 allFeedback을 호출하게 만들고 토큰을 가로챈다
        page.goto(FEEDBACK_PAGE, wait_until="networkidle")
        for _ in range(20):
            if captured["token"]:
                break
            time.sleep(0.5)
        browser.close()
    if not captured["token"]:
        raise SystemExit("❌ accesstoken 캡처 실패 — 로그인 흐름/셀렉터 확인 필요")
    return captured["token"]


def fetch_month(token, ym):
    r = requests.get(
        API.format(ym=ym),
        headers={"accesstoken": token, "accept": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    j = r.json()
    if not j.get("success"):
        raise SystemExit(f"❌ {ym}: API success=false ({j.get('message')})")
    return j


def main():
    email = os.environ.get("CARROT_EMAIL", "").strip()
    password = os.environ.get("CARROT_PASSWORD", "").strip()
    if not email or not password:
        raise SystemExit("❌ CARROT_EMAIL / CARROT_PASSWORD 환경변수 필요")

    months = target_months(sys.argv[1:])
    os.makedirs(CARROT, exist_ok=True)
    print(f"🔐 로그인 중... ({email[:3]}…)")
    token = login_and_get_token(email, password)
    print("✅ accesstoken 확보")

    for ym in months:
        data = fetch_month(token, ym)
        n = len((data.get("data") or {}).get("list") or [])
        path = os.path.join(CARROT, f"{ym}.json")
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"💾 {ym}: {n}일 → docs/carrot/{ym}.json")

    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d")
    open(os.path.join(CARROT, "_fetched.txt"), "w", encoding="utf-8").write(stamp)
    print(f"🗓 갱신일 기록: {stamp}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
당근 로그인 화면 회귀 검사 / regression test for the Carrot login selectors (네트워크 미사용).

2026-11-06 실측 구조를 그대로 흉내 낸다: '다음'·'로그인' 은 <button> 이 아니라 클릭되는 <p> 글자이고,
브라우저 언어에 따라 영어 화면("Next")이 나온다 → 10/18·10/25·11/02 수집이 '비밀번호 칸 없음'으로 실패했다.
실행 / run:  python3 tests/test_carrot_login.py   (playwright·chromium 이 없으면 건너뜀)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

PAGE = """<html lang="{lang}"><body><div>
<label>{label}</label><input type="{itype}" id="user{iid}" placeholder="{ph}">
<div onclick="document.body.dataset.clicked='{what}'"><p class="cursor-pointer">{text}</p></div>
<p>{other}</p></div></body></html>"""


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP playwright 없음")
        return 0
    import fetch_carrot_feedback as F

    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    cases = [
        ("영어 이메일 화면: Next 글자", "en", "email", "Email", "Enter your email", "Next", "Forgot password?", F.next_candidates, "next"),
        ("한국어 이메일 화면: 다음 글자", "ko", "email", "Email", "이메일을 입력해주세요", "다음", "비밀번호 찾기", F.next_candidates, "next"),
        ("영어 비밀번호 화면: Log in 글자", "en", "password", "Pw", "Enter your password", "Log in", "Forgot password?", F.login_candidates, "login"),
        ("한국어 비밀번호 화면: 로그인 하기 글자", "ko", "password", "Pw", "비밀번호", "로그인 하기", "로그인 정보 찾기", F.login_candidates, "login"),
    ]
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for name, lang, itype, iid, ph, text, other, cands, what in cases:
                page = browser.new_page()
                page.set_content(PAGE.format(lang=lang, itype=itype, iid=iid, ph=ph, text=text, other=other,
                                             label=ph, what=what))
                try:
                    F._resolve(page, cands(page), name, timeout_ms=2000).click()
                    check(name, page.evaluate("document.body.dataset.clicked") == what)
                except F.LoginError as e:
                    check(f"{name} ({e})", False)
                page.close()
            browser.close()
    except Exception as e:  # noqa: BLE001 — 브라우저가 없으면 건너뜀
        if "Executable doesn't exist" in str(e):
            print("SKIP chromium 없음")
            return 0
        raise
    check("다른 글자('비밀번호 찾기' 등)는 안 누름", not F.LOGIN_TEXT.match("로그인 정보 찾기") and not F.NEXT_TEXT.match("다음에 하기"))

    print(f"\n{'ALL PASS' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

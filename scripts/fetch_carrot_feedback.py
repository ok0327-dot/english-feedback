#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🥕 Carrot English 강사 공식 피드백 수집기 / fetcher.

로그인은 두 갈래다 / two login paths:
  ① API 우선(기본) — 사이트 화면이 내부적으로 부르는 로그인 API(POST /app/auth/login
     {uid, password})를 직접 불러 data.accessToken 을 받는다. 화면 글자·언어·로딩 타이밍과
     무관하므로, 2026-09~11 의 '다음 눌러도 안 넘어감' 실패 6건이 구조적으로 생기지 않는다.
  ② 브라우저 예비(fallback) — ①이 거절 외의 이유(네트워크·HTTP 오류·응답 모양 변경·토큰 검증
     실패)로 안 되면 기존 Playwright 로그인으로 앱 요청의 accesstoken 헤더를 가로챈다.
  서버가 비밀번호를 명시적으로 거절하면(success=false) 브라우저로 같은 비밀번호를 다시 보내지
  않고 바로 끝낸다(exit 5) — 틀린 비밀번호 반복 제출로 계정이 잠기는 것을 막는다.
그 토큰으로 allFeedback API 를 월별 호출 → docs/carrot/YYYY-MM.json 저장.
① API-first: call the login API the web app itself uses; ② fall back to the headless-browser
flow only for non-rejection failures. An explicit credential rejection exits 5 immediately.

자격증명은 환경변수로만 받는다(절대 하드코딩/커밋 금지):
Credentials come from env vars only — never hardcode or commit them:
  CARROT_EMAIL, CARROT_PASSWORD
선택 환경변수 / optional:
  CARROT_DEBUG_DIR  실패 시 스크린샷·HTML 덤프 경로(기본 <repo>/debug-carrot)

CLI:
  python3 scripts/fetch_carrot_feedback.py                  # 이번 달 + 지난 달
  python3 scripts/fetch_carrot_feedback.py 2026-06 2026-07  # 특정 월(들)
  python3 scripts/fetch_carrot_feedback.py --backfill       # 빠진 달만 채우기(기본 2026-02~)
  python3 scripts/fetch_carrot_feedback.py --backfill --since 2026-01

종료 코드 / exit codes:
  0 성공(success) / 2 자격증명 미설정(missing credentials)
  3 로그인·토큰 캡처 실패 — API·브라우저 둘 다(login failed on both paths)
  4 API 호출 실패(API call failed)
  5 서버가 이메일·비밀번호를 거절(credentials rejected by the server)

백필은 '빠진 달' + '그 달이 끝나기 전에(말일+7일 전) 받은 달'을 다시 받는다 — 실패가 길어져
달을 넘기면 덜 받은 달이 그대로 굳던 문제(2026-06: 06-26 에 받은 뒤 갱신 안 됨) 방지.
Backfill also re-fetches months that were last fetched before they were over.

의존성: pip install requests (브라우저 예비 경로용: playwright + python -m playwright install chromium)
"""
import os, sys, re, json, glob, html, datetime, time, argparse
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARROT = os.path.join(ROOT, "docs", "carrot")
DEBUG_DIR = os.environ.get("CARROT_DEBUG_DIR") or os.path.join(ROOT, "debug-carrot")
KST = datetime.timezone(datetime.timedelta(hours=9))

LOGIN_URL = "https://carrotfarm.carrotenglish.com/auth/startEmail"
FEEDBACK_PAGE = "https://carrotfarm.carrotenglish.com/myClassroom/feedback?idxLecture=0"
API = "https://homeapi.carrotenglish.com/app/myclass/allFeedback?searchYM={ym}"
# 사이트 공개 코드(assets/startEmailAlready.*.js, 2026-11-15 확인)의 로그인 호출과 같은 주소·본문.
# Same endpoint/body as the site's own login call (public bundle, checked 2026-11-15).
LOGIN_API = "https://homeapi.carrotenglish.com/app/auth/login"

# 종료 코드 상수 / exit code constants
EXIT_OK, EXIT_NO_CREDS, EXIT_LOGIN, EXIT_API, EXIT_REJECTED = 0, 2, 3, 4, 5

DEFAULT_SINCE = "2026-02"          # 백필 기본 시작 월 / default backfill start
LOGIN_ATTEMPTS = 3                 # 최초 1회 + 재시도 2회 / initial + 2 retries
API_ATTEMPTS = 3                   # 네트워크 오류 시 재시도 포함 / incl. retries
# 강사가 피드백을 며칠 늦게 쓰기도 하므로, '다음 달 1일 + 7일' 이후에 받은 파일만 그 달의 완결본으로 본다.
# A month counts as final only if fetched on/after the 1st of the next month + this grace.
FINAL_GRACE_DAYS = 7
YM_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class LoginError(RuntimeError):
    """로그인/토큰 캡처 단계 실패 / login or token-capture failure."""


class CredentialsRejected(RuntimeError):
    """
    서버가 이메일·비밀번호를 명시적으로 거절(success=false). LoginError 와 일부러 별개 —
    재시도·브라우저 예비 경로가 이걸 잡아 같은 비밀번호를 또 보내면 안 된다.
    Explicit rejection; deliberately NOT a LoginError so no retry path resends the password.
    """


class ApiError(RuntimeError):
    """allFeedback API 호출 실패 / allFeedback API failure."""


def err(msg):
    """실패 메시지는 stderr로 / failures go to stderr."""
    print(msg, file=sys.stderr)


# ────────────────────────────── 월 계산 / month planning ──────────────────────────────
def _ym(date):
    return date.strftime("%Y-%m")


def current_and_previous_month():
    """이번 달, 지난 달 / current and previous month (KST 기준)."""
    today = datetime.datetime.now(KST).date()
    first = today.replace(day=1)
    prev = first - datetime.timedelta(days=1)
    return _ym(today), _ym(prev)


def month_range(since, until):
    """since~until(포함) 월 목록을 오름차순으로 / inclusive ascending month list."""
    y, m = (int(x) for x in since.split("-"))
    ey, em = (int(x) for x in until.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def existing_months():
    """docs/carrot/ 에 이미 있는 월 / months already saved on disk."""
    found = set()
    for path in glob.glob(os.path.join(CARROT, "*.json")):
        name = os.path.basename(path)[:-5]
        if YM_RE.match(name):
            found.add(name)
    return found


def load_meta():
    """기존 _meta.json(없거나 깨졌으면 빈 dict) / previous meta, or {} if absent/broken."""
    try:
        with open(os.path.join(CARROT, "_meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        return meta if isinstance(meta, dict) else {}
    except (OSError, ValueError):
        return {}


def month_final_date(ym):
    """이 날짜 이후에 받았다면 그 달은 완결본 / fetched on/after this date ⇒ month is final."""
    y, m = (int(x) for x in ym.split("-"))
    first_of_next = datetime.date(y + (m == 12), m % 12 + 1, 1)
    return first_of_next + datetime.timedelta(days=FINAL_GRACE_DAYS)


def is_final(ym, fetched_on):
    """
    fetched_on[ym](YYYY-MM-DD)이 그 달 완결 기준일 이후인가. 기록이 없으면 미완결로 본다
    → 이 기능 도입 직후 한 번은 모든 달을 다시 받는다(약 10회 호출, 덜 받은 달 자가 복구).
    No record ⇒ not final, so the first run after rollout re-fetches every month once.
    """
    try:
        return datetime.date.fromisoformat(str(fetched_on.get(ym))) >= month_final_date(ym)
    except (TypeError, ValueError):
        return False


def plan_months(args, have=None, fetched_on=None):
    """수집 대상 월 목록을 최신순으로 계산 / resolve target months, newest first."""
    cur, prev = current_and_previous_month()

    if args.months:
        return list(args.months)

    if args.backfill:
        have = existing_months() if have is None else have
        if fetched_on is None:
            fetched_on = load_meta().get("fetched_on") or {}
        # 파일이 없는 달 + 끝나기 전에 받은 달 + 진행 중인 이번/지난 달(있어도 항상 갱신)
        # missing + fetched-before-it-ended + the two in-flight months (always refreshed)
        wanted = [ym for ym in month_range(args.since, cur)
                  if ym not in have or not is_final(ym, fetched_on)]
        for ym in (cur, prev):
            if ym >= args.since:
                wanted.append(ym)
        return sorted(set(wanted), reverse=True)

    return [cur, prev]


# ────────────────────────────── 디버그 덤프 / debug dump ──────────────────────────────
def _mask(text, secrets):
    """이메일·비밀번호 원문을 *** 로 치환 / scrub raw credentials from a dump."""
    for secret in secrets:
        if not secret:
            continue
        for variant in {secret, html.escape(secret), secret.replace("@", "%40")}:
            text = text.replace(variant, "***")
    # 안전망: 모든 <input ... value="..."> 를 마스킹 / safety net for input values
    text = re.sub(r'(<input\b[^>]*?\bvalue=")[^"]*(")', r"\1***\2", text, flags=re.I)
    return text


def write_reason(text):
    """
    실패 이유 한 줄을 DEBUG_DIR/reason.txt 에 — 워크플로가 텔레그램 알림에 붙인다(마스킹된 값만 넘길 것).
    One-line failure reason for the workflow's alert (callers pass already-masked text).
    """
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        with open(os.path.join(DEBUG_DIR, "reason.txt"), "w", encoding="utf-8") as f:
            f.write(" ".join(str(text).split())[:300] + "\n")
    except OSError as e:
        err(f"⚠️ reason.txt 기록 실패 / could not write reason: {e}")


def dump_debug(page, secrets, tag="login-failure"):
    """실패 화면 스크린샷 + HTML 저장(자격증명 마스킹) / save masked screenshot + HTML."""
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        # 스크린샷에 입력값이 찍히지 않도록 먼저 비운다 / blank inputs before shooting
        try:
            page.evaluate(
                "() => document.querySelectorAll('input').forEach(i => { i.value = '***'; })"
            )
        except Exception:
            pass
        shot = os.path.join(DEBUG_DIR, f"{tag}.png")
        page.screenshot(path=shot, full_page=True)
        doc = os.path.join(DEBUG_DIR, f"{tag}.html")
        with open(doc, "w", encoding="utf-8") as f:
            f.write(_mask(page.content(), secrets))
        print(f"🧾 디버그 덤프 저장 / debug dump: {shot} , {doc}")
    except Exception as e:  # 덤프 실패가 원인 오류를 가리지 않게 / never mask root cause
        err(f"⚠️ 디버그 덤프 실패 / debug dump failed: {type(e).__name__}: {e}")


# ────────────────────────────── 로그인 / login ──────────────────────────────
def _resolve(page, factories, label, timeout_ms=15000):
    """
    셀렉터 fallback 체인에서 처음 보이는 요소를 반환.
    Return the first visible element from a fallback chain of selectors.
    """
    deadline = time.time() + timeout_ms / 1000.0
    last = None
    while True:
        for i, factory in enumerate(factories, 1):
            try:
                loc = factory().first
                if loc.count() > 0 and loc.is_visible():
                    print(f"   ↳ {label}: 후보 #{i} 매칭 / matched candidate #{i}")
                    return loc
            except Exception as e:
                last = e
        if time.time() >= deadline:
            break
        page.wait_for_timeout(500)
    raise LoginError(f"{label} 요소를 찾지 못함 / element not found ({last})")


# '다음'·'로그인' 은 <button> 이 아니라 클릭되는 글자(<p class="cursor-pointer">)다 (2026-11-06 실측, 한국어·영어 화면 모두).
# 그래서 버튼 역할보다 '정확히 그 글자'를 먼저 찾고, 한국어·영어 둘 다 받는다. Enter 키는 form 이 없어 아무 일도 안 한다.
# The "Next"/"Log in" controls are clickable <p> text, not buttons — match the exact text first, in both languages.
NEXT_TEXT = re.compile(r"^\s*(다음|next|continue)\s*$", re.I)
LOGIN_TEXT = re.compile(r"^\s*(로그인(\s*하기)?|log\s?in|sign\s?in)\s*$", re.I)


def next_candidates(page):
    return [
        lambda: page.get_by_text(NEXT_TEXT),
        lambda: page.get_by_role("button", name=NEXT_TEXT),
        lambda: page.locator("button[type=submit], input[type=submit]"),
    ]


def login_candidates(page):
    return [
        lambda: page.get_by_text(LOGIN_TEXT),
        lambda: page.get_by_role("button", name=LOGIN_TEXT),
        lambda: page.locator("button[type=submit], input[type=submit]"),
    ]


def _login_once(email, password):
    """로그인 1회 시도 → accesstoken 반환 / one login attempt returning the token."""
    # 워크플로의 브라우저 설치 단계는 실패해도 계속 간다(API 경로엔 불필요). 그래서 여기서 없으면
    # 잡히지 않는 예외(exit 1) 대신 LoginError 로 바꿔 종료 코드 계약(3)을 지킨다.
    # The workflow's browser install may fail softly; keep the exit-code contract if it did.
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise LoginError(f"playwright 미설치 / not installed ({e})") from e

    captured = {"token": None}
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:  # noqa: BLE001 — 예: chromium 미설치 / e.g. browser binary missing
            raise LoginError(f"chromium 실행 실패 / launch failed: {type(e).__name__}: {e}") from e
        # 한국어 화면으로 고정 — 2026-10 부터 사이트가 브라우저 언어를 따라 영어 화면("Next")을 주는데,
        # GitHub 실행 환경은 영어라서 '다음' 을 못 찾고 3주 연속 로그인 실패했다(10/18·10/25·11/02).
        # Pin the Korean UI: the site now follows the browser locale and the English UI broke the selectors.
        page = browser.new_context(locale="ko-KR", extra_http_headers={"Accept-Language": "ko-KR,ko;q=0.9"}).new_page()

        # 세션 리플레이 비콘(replays.carrotsolutions.co.kr → 2026-11 부터 replay.…)은 스트리밍이라 요청이 끝나지 않는다.
        # 수집에 불필요하므로 아예 차단해 페이지 로드를 가볍게 만든다.
        # The session-replay beacon streams and never completes; it is irrelevant here, so block it.
        page.route(re.compile(r"replays?\.carrotsolutions\.co\.kr"), lambda r: r.abort())

        # 로그인 API 응답 코드를 로그에 남긴다 — 다음 실패 때 '눌렀는데 안 넘어감'의 원인을 바로 보게.
        def on_response(res):
            if "homeapi.carrotenglish.com/app/auth" in res.url:
                print(f"   ↳ 로그인 API / auth API {res.url.split('/app/auth/')[-1].split('?')[0]} → {res.status}")
        page.on("response", on_response)

        def on_request(req):
            # allFeedback 우선, 없으면 homeapi 로 가는 인증 요청에서라도 확보
            # prefer allFeedback, else any authenticated homeapi request
            if captured["token"]:
                return
            tok = req.headers.get("accesstoken")
            if tok and ("allFeedback" in req.url or "homeapi.carrotenglish.com" in req.url):
                captured["token"] = tok

        page.on("request", on_request)
        try:
            print(f"🌐 [1/6] 로그인 페이지 이동 / open login page: {LOGIN_URL}")
            # ⚠️ wait_until="networkidle" 금지. 이 사이트는 끝나지 않는 분석 요청을 물고 있어
            #    networkidle 이 영원히 만족되지 않고 100% 타임아웃한다(실측: 8주 연속 CI 실패 원인).
            #    대신 DOM 준비만 기다리고, 실제로 필요한 요소를 _resolve() 로 폴링한다.
            # ⚠️ Never use networkidle here: a never-ending analytics request makes it time out
            #    deterministically. Wait for the DOM, then poll for the element we actually need.
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
            # 화면 프로그램(Vue)이 붙기 전에 입력하면 값이 지워져 '다음'을 눌러도 넘어가지 않는다
            # (2026-11-06: CI 에서 '다음' 클릭 후에도 이메일 화면에 머묾, 3초 기다린 로컬은 정상) → load 까지 기다린다.
            try:
                page.wait_for_load_state("load", timeout=20000)
            except Exception:  # noqa: BLE001 — 분석 스크립트가 늦어도 아래 폴링이 요소를 기다린다
                pass
            page.wait_for_timeout(1500)

            for attempt in (1, 2):  # '다음'을 눌렀는데 그대로면 한 번 더
                print(f"✍️ [2/6] 이메일 입력 / fill email ({attempt})")
                box = _resolve(page, [
                    lambda: page.get_by_placeholder("이메일"),
                    lambda: page.locator("input[type=email]"),
                    lambda: page.locator("input[name*=email i], input[id*=email i]"),
                    lambda: page.get_by_role("textbox"),
                ], "이메일 입력칸 / email field")
                box.fill(email)
                if box.input_value() != email:  # 값이 안 남았으면 한 글자씩 다시
                    print("   ↳ 입력값이 남지 않음 → 한 글자씩 다시 입력 / retyping")
                    box.fill("")
                    box.press_sequentially(email, delay=40)

                print("➡️ [3/6] '다음' 진행 / submit email step")
                try:
                    _resolve(page, next_candidates(page), "다음 버튼 / next button", timeout_ms=8000).click()
                except LoginError:
                    # 최후 수단: Enter 키 제출 / last resort: submit with Enter
                    print("   ↳ 버튼 없음 → Enter 키로 제출 / falling back to Enter")
                    page.keyboard.press("Enter")
                try:
                    page.locator("input[type=password]").first.wait_for(state="visible", timeout=12000)
                    break
                except Exception:  # noqa: BLE001
                    print(f"   ↳ '다음' 뒤에도 비밀번호 화면이 안 나옴 (url={page.url}) / still on email step")

            print("🔑 [4/6] 비밀번호 입력 / fill password")
            _resolve(page, [
                lambda: page.get_by_placeholder("비밀번호"),
                lambda: page.locator("input[type=password]"),
                lambda: page.locator("input[name*=pass i], input[id*=pass i]"),
            ], "비밀번호 입력칸 / password field").fill(password)

            print("🚪 [5/6] '로그인 하기' 클릭 / submit login")
            try:
                _resolve(page, login_candidates(page), "로그인 버튼 / login button", timeout_ms=8000).click()
            except LoginError:
                print("   ↳ 버튼 없음 → Enter 키로 제출 / falling back to Enter")
                page.keyboard.press("Enter")

            page.wait_for_url("**/myClassroom**", timeout=25000)
            print("🏫 로그인 성공 — myClassroom 진입 / logged in")

            print("📡 [6/6] 피드백 페이지에서 accesstoken 캡처 / capture token")
            # 위와 같은 이유로 networkidle 금지. 토큰은 아래 폴링으로 기다린다.
            # networkidle is unusable here for the same reason; the poll below waits for the token.
            page.goto(FEEDBACK_PAGE, wait_until="domcontentloaded", timeout=45000)
            for _ in range(40):
                if captured["token"]:
                    break
                page.wait_for_timeout(500)

            if not captured["token"]:
                raise LoginError("accesstoken 캡처 실패 / token not captured")
            return captured["token"]
        except Exception as e:
            dump_debug(page, [email, password])
            if isinstance(e, LoginError):
                raise
            raise LoginError(f"{type(e).__name__}: {e}") from e
        finally:
            browser.close()


def login_and_get_token(email, password):
    """지수 백오프로 재시도하며 로그인 / login with exponential backoff retries."""
    last = None
    for attempt in range(1, LOGIN_ATTEMPTS + 1):
        try:
            print(f"🔐 로그인 시도 {attempt}/{LOGIN_ATTEMPTS} / login attempt")
            return _login_once(email, password)
        except LoginError as e:
            last = e
            err(f"⚠️ 로그인 실패({attempt}/{LOGIN_ATTEMPTS}) / login failed: {e}")
            if attempt < LOGIN_ATTEMPTS:
                delay = 3 * (2 ** (attempt - 1))  # 3s → 6s
                print(f"⏳ {delay}초 후 재시도 / retrying in {delay}s")
                time.sleep(delay)
    raise LoginError(str(last))


def _short(text, secrets, limit=200):
    """서버 메시지를 알림에 실을 수 있게: 자격증명 가리고 한 줄로 자르기 / mask + one line + trim."""
    text = _mask(str(text or ""), secrets)
    return " ".join(text.split())[:limit]


def api_login(email, password):
    """
    화면을 거치지 않고 사이트의 로그인 API 를 직접 부른다(1회, 재시도 없음).
    Call the site's login API directly — once, no retry (never resend a password blindly).

    성공 → accessToken / 서버 거절(HTTP 200·success=false) → CredentialsRejected
    그 밖의 모든 이상(연결·HTTP·JSON·토큰 없음) → LoginError (→ 브라우저 예비 경로)
    """
    try:
        r = requests.post(
            LOGIN_API,
            json={"uid": email, "password": password},
            headers={"accept": "application/json"},
            timeout=30,
        )
    except requests.RequestException as e:
        raise LoginError(f"로그인 API 연결 실패 / connection failed: {type(e).__name__}") from e
    if r.status_code == 401:
        # 인증 거절을 HTTP 로 알린 경우 — 브라우저로 같은 비밀번호를 또 보내지 않는다(코덱스 검토 반영).
        # 403 은 봇 차단(WAF)일 수 있어 브라우저 예비 경로로 보낸다. 403 may be a bot wall → fallback.
        raise CredentialsRejected("Carrot 로그인 API HTTP 401 / unauthorized")
    if r.status_code != 200:
        raise LoginError(f"로그인 API HTTP {r.status_code}")
    try:
        j = r.json()
    except ValueError as e:
        raise LoginError("로그인 API 응답이 JSON 이 아님 / non-JSON response") from e
    if not isinstance(j, dict):
        raise LoginError("로그인 API 응답 모양이 다름 / unexpected response shape")
    if j.get("success") is False:
        msg = _short(j.get("message"), [email, password]) or "message 없음"
        raise CredentialsRejected(f"Carrot 서버가 로그인을 거절 / rejected: {msg}")
    data = j.get("data") if isinstance(j.get("data"), dict) else {}
    token = data.get("accessToken")
    if j.get("success") is not True or not isinstance(token, str) or not token:
        raise LoginError("로그인 API 응답에 accessToken 없음 / no accessToken in response")
    return token


def _gh_warning(title, msg):
    """Actions 실행 화면에 노란 경고로 띄운다(로컬에선 그냥 한 줄) / yellow annotation on Actions."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning title={title}::{msg}")
    else:
        print(f"⚠️ {title}: {msg}")


def get_token(email, password):
    """
    API 로그인 우선, 안 되면 브라우저 → (token, "api" | "browser").
    API first; fall back to the browser flow on any non-rejection failure.
    CredentialsRejected 는 그대로 올려 보낸다(브라우저로 같은 비밀번호 재전송 금지).
    """
    cur, _ = current_and_previous_month()
    try:
        print("🔐 API 로그인 / API login")
        token = api_login(email, password)
        try:
            fetch_month(token, cur)  # 실제 수집 API 로 토큰 검증 / verify on the real data API
            print("✅ API 로그인 성공 — 브라우저 불필요 / API login ok, browser not needed")
            return token, "api"
        except ApiError as e:
            reason = f"API 토큰 검증 실패 / token rejected by data API: {e}"
    except LoginError as e:
        reason = str(e)
    _gh_warning("Carrot 브라우저 예비 경로", f"{reason} → 브라우저 로그인으로 전환 / falling back to browser")
    try:
        return login_and_get_token(email, password), "browser"
    except LoginError as e:
        # 브라우저 쪽 이유(예: playwright 미설치)가 API 쪽 진짜 원인을 가리지 않게 둘 다 싣는다.
        # Report both causes so a browser-side error never hides the API-side one.
        raise LoginError(f"API: {reason} | 브라우저/browser: {e}") from e


# ────────────────────────────── API ──────────────────────────────
def fetch_month(token, ym):
    """한 달치 피드백을 받아온다(네트워크 오류 시 재시도) / fetch one month with retries."""
    last = None
    for attempt in range(1, API_ATTEMPTS + 1):
        try:
            r = requests.get(
                API.format(ym=ym),
                headers={"accesstoken": token, "accept": "application/json"},
                timeout=30,
            )
            if r.status_code >= 500:  # 일시적 장애 → 재시도 / transient, retry
                raise requests.RequestException(f"HTTP {r.status_code}")
            if r.status_code >= 400:  # 인증·요청 오류 → 즉시 실패 / permanent
                raise ApiError(f"{ym}: HTTP {r.status_code}")
            j = r.json()
            if not j.get("success"):
                raise ApiError(f"{ym}: API success=false ({j.get('message')})")
            # 요청한 달의 자료가 맞는지 확인 — 서버가 searchYM 을 무시하고 다른 달을 주면, 백필이 지난 달
            # 파일들을 엉뚱한 자료로 덮어쓴다. 저장 전에 막는다(코덱스 검토 반영).
            # Refuse data whose createDate is outside the requested month before it overwrites a file.
            items = (j.get("data") or {}).get("list") or []
            stray = [x for x in items if not str((x or {}).get("createDate") or "").startswith(ym)]
            if stray:
                raise ApiError(f"{ym}: 다른 달 자료 {len(stray)}건 섞임 / {len(stray)} item(s) outside the month "
                               f"(예: {str((stray[0] or {}).get('createDate'))[:10]})")
            return j
        except ApiError:
            raise
        except (requests.RequestException, ValueError) as e:
            last = e
            err(f"⚠️ {ym} 요청 실패({attempt}/{API_ATTEMPTS}) / request failed: {e}")
            if attempt < API_ATTEMPTS:
                time.sleep(2 * (2 ** (attempt - 1)))  # 2s → 4s
    raise ApiError(f"{ym}: 네트워크 오류로 실패 / network failure ({last})")


# ────────────────────────────── 기록 / bookkeeping ──────────────────────────────
def month_day_count(path):
    """저장된 월 파일의 수업일 수 / number of class days in a saved month file."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return len((data.get("data") or {}).get("list") or [])
    except Exception:
        return 0


def write_stamps(fetched_months, login_via=None):
    """_fetched.txt(기존 호환) + _meta.json 기록 / write both stamp files."""
    now = datetime.datetime.now(KST)
    stamp = now.strftime("%Y-%m-%d")
    with open(os.path.join(CARROT, "_fetched.txt"), "w", encoding="utf-8") as f:
        f.write(stamp)

    # 달별 마지막 수집일 — 백필이 '끝나기 전에 받은 달'을 알아보는 근거 / per-month last fetch date
    fetched_on = dict(load_meta().get("fetched_on") or {})
    for ym in fetched_months:
        fetched_on[ym] = stamp

    # docs/carrot/ 전체를 스캔해 월별 일수·총계 산출 / scan the whole dir for counts
    counts = {ym: month_day_count(os.path.join(CARROT, f"{ym}.json"))
              for ym in sorted(existing_months())}
    meta = {
        "fetched_at": stamp,
        "fetched_at_iso": now.isoformat(timespec="seconds"),
        "months": list(fetched_months),
        "counts": counts,
        "total_days": sum(counts.values()),
        "fetched_on": dict(sorted(fetched_on.items())),
        # 어느 로그인 경로로 받았나 — "browser" 가 보이면 API 경로가 조용히 깨진 것
        # which login path worked; "browser" here means the API path silently broke
        "login_via": login_via,
    }
    with open(os.path.join(CARROT, "_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"🗓 갱신일 기록 / stamped: {stamp} (총 {meta['total_days']}일, {len(counts)}개월)")


# ────────────────────────────── main ──────────────────────────────
def parse_args(argv):
    ap = argparse.ArgumentParser(
        description="Carrot English 강사 피드백 수집기 / feedback fetcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("months", nargs="*", help="수집할 월(YYYY-MM). 생략 시 이번 달+지난 달")
    ap.add_argument("--backfill", action="store_true",
                    help="docs/carrot/ 에 없는 달만 채운다 / fill gaps only")
    ap.add_argument("--since", default=DEFAULT_SINCE, metavar="YYYY-MM",
                    help=f"백필 시작 월 / backfill start (기본 {DEFAULT_SINCE})")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    bad = [ym for ym in list(args.months) + [args.since] if not YM_RE.match(ym)]
    if bad:
        err(f"❌ 월 형식은 YYYY-MM 이어야 합니다 / bad month format: {', '.join(bad)}")
        return EXIT_NO_CREDS

    email = os.environ.get("CARROT_EMAIL", "").strip()
    password = os.environ.get("CARROT_PASSWORD", "").strip()
    if not email or not password:
        err("❌ CARROT_EMAIL / CARROT_PASSWORD 환경변수가 없습니다 / credentials not set")
        err("   → GitHub → Settings → Secrets and variables → Actions 에서")
        err("     CARROT_EMAIL / CARROT_PASSWORD 를 추가하세요.")
        err("   → Add both secrets at: GitHub → Settings → Secrets and variables → Actions")
        err("   → 로컬 실행: CARROT_EMAIL=… CARROT_PASSWORD=… python3 scripts/fetch_carrot_feedback.py")
        return EXIT_NO_CREDS

    os.makedirs(CARROT, exist_ok=True)
    months = plan_months(args)
    if not months:
        print("✅ 수집할 달이 없습니다 — 모든 월이 이미 채워져 있습니다 / nothing to fetch")
        return EXIT_OK
    print(f"📅 대상 월 / target months: {', '.join(months)}")

    try:
        token, via = get_token(email, password)
    except CredentialsRejected as e:
        err(f"❌ {e}")
        err("   → 비밀번호를 바꿨다면 CARROT_PASSWORD 시크릿을 새 값으로 다시 등록하세요.")
        err("   → If you changed the password, re-set the CARROT_PASSWORD secret.")
        err("   → 계정 잠김을 막으려고 브라우저로 다시 시도하지 않았습니다 / not retried to avoid a lockout.")
        write_reason(str(e))
        return EXIT_REJECTED
    except LoginError as e:
        err(f"❌ 로그인/accesstoken 캡처 실패(API·브라우저 모두) / login failed on both paths: {e}")
        err("   → Carrot 로그인 API 또는 화면이 바뀌었을 수 있습니다 / the login API or UI changed.")
        err(f"   → 덤프 확인 / check dump: {DEBUG_DIR}")
        write_reason(_short(e, [email, password]))
        return EXIT_LOGIN
    print(f"✅ accesstoken 확보({via}) / token acquired via {via}")

    saved, failed = [], []
    for ym in months:
        try:
            data = fetch_month(token, ym)
        except ApiError as e:
            err(f"❌ {e}")
            failed.append(ym)
            continue
        n = len((data.get("data") or {}).get("list") or [])
        path = os.path.join(CARROT, f"{ym}.json")
        old_n = month_day_count(path) if os.path.exists(path) else 0
        saved.append(ym)
        if n < old_n:
            # 다시 받았더니 일수가 줄었다 → 서버 쪽 일시 이상일 수 있으니 기록을 잃지 않게 기존 파일 유지
            # Fewer days than what we already have — keep the richer file rather than lose records.
            _gh_warning("Carrot 일수 감소", f"{ym}: 새로 받은 {n}일 < 저장된 {old_n}일 — 기존 파일 유지 / kept existing")
            continue
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        if n == 0:
            print(f"⚠️ {ym}: 0일 — 수업이 없었거나 아직 미등록 / empty month (not an error)")
        dates = sorted(str(x.get("createDate"))[5:10] for x in (data.get("data") or {}).get("list") or [])
        span = f" [{dates[0]}~{dates[-1]}]" if dates else ""
        print(f"💾 {ym}: {n}일{span} → docs/carrot/{ym}.json" + (f" (이전 {old_n}일)" if n != old_n else ""))

    if saved:
        write_stamps(saved, via)

    if failed:
        err(f"❌ 실패한 달 / failed months: {', '.join(failed)}")
        return EXIT_API
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🥕 Carrot English 강사 공식 피드백 수집기 / fetcher.

이메일+비밀번호로 로그인(Playwright headless) → 앱이 보내는 요청의 accesstoken
헤더를 가로채 → 그 토큰으로 allFeedback API를 월별 호출 → docs/carrot/YYYY-MM.json 저장.
(저장소 토큰 스캐닝이 아니라 '앱 자신의 요청 헤더'를 캡처하는 방식.)
Login with email+password (headless Playwright), intercept the `accesstoken` header the
app itself sends, then call the monthly allFeedback API with that token.

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
  3 로그인·토큰 캡처 실패(login or token capture failed) / 4 API 호출 실패(API call failed)

의존성: pip install playwright requests 후 python -m playwright install chromium
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

# 종료 코드 상수 / exit code constants
EXIT_OK, EXIT_NO_CREDS, EXIT_LOGIN, EXIT_API = 0, 2, 3, 4

DEFAULT_SINCE = "2026-02"          # 백필 기본 시작 월 / default backfill start
LOGIN_ATTEMPTS = 3                 # 최초 1회 + 재시도 2회 / initial + 2 retries
API_ATTEMPTS = 3                   # 네트워크 오류 시 재시도 포함 / incl. retries
YM_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class LoginError(RuntimeError):
    """로그인/토큰 캡처 단계 실패 / login or token-capture failure."""


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


def plan_months(args):
    """수집 대상 월 목록을 최신순으로 계산 / resolve target months, newest first."""
    cur, prev = current_and_previous_month()

    if args.months:
        return list(args.months)

    if args.backfill:
        have = existing_months()
        # 파일이 없는 달 + 진행 중인 이번/지난 달(있어도 항상 갱신)
        # missing months + the two in-flight months (always refreshed)
        wanted = [ym for ym in month_range(args.since, cur) if ym not in have]
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


def _login_once(email, password):
    """로그인 1회 시도 → accesstoken 반환 / one login attempt returning the token."""
    from playwright.sync_api import sync_playwright

    captured = {"token": None}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context().new_page()

        # 세션 리플레이 비콘(replays.carrotsolutions.co.kr)은 스트리밍이라 요청이 끝나지 않는다.
        # 수집에 불필요하므로 아예 차단해 페이지 로드를 가볍게 만든다.
        # The session-replay beacon streams and never completes; it is irrelevant here, so block it.
        page.route(re.compile(r"replays\.carrotsolutions\.co\.kr"), lambda r: r.abort())

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

            print("✍️ [2/6] 이메일 입력 / fill email")
            _resolve(page, [
                lambda: page.get_by_placeholder("이메일"),
                lambda: page.locator("input[type=email]"),
                lambda: page.locator("input[name*=email i], input[id*=email i]"),
                lambda: page.get_by_role("textbox"),
            ], "이메일 입력칸 / email field").fill(email)

            print("➡️ [3/6] '다음' 진행 / submit email step")
            try:
                _resolve(page, [
                    lambda: page.get_by_role("button", name=re.compile("다음|next", re.I)),
                    lambda: page.get_by_text("다음", exact=True),
                    lambda: page.locator("button[type=submit], input[type=submit]"),
                    lambda: page.get_by_role("button"),
                ], "다음 버튼 / next button", timeout_ms=8000).click()
            except LoginError:
                # 최후 수단: Enter 키 제출 / last resort: submit with Enter
                print("   ↳ 버튼 없음 → Enter 키로 제출 / falling back to Enter")
                page.keyboard.press("Enter")

            print("🔑 [4/6] 비밀번호 입력 / fill password")
            _resolve(page, [
                lambda: page.get_by_placeholder("비밀번호"),
                lambda: page.locator("input[type=password]"),
                lambda: page.locator("input[name*=pass i], input[id*=pass i]"),
            ], "비밀번호 입력칸 / password field").fill(password)

            print("🚪 [5/6] '로그인 하기' 클릭 / submit login")
            try:
                _resolve(page, [
                    lambda: page.get_by_role("button", name=re.compile("로그인|log ?in|sign ?in", re.I)),
                    lambda: page.get_by_text(re.compile("로그인")),
                    lambda: page.locator("button[type=submit], input[type=submit]"),
                    lambda: page.get_by_role("button"),
                ], "로그인 버튼 / login button", timeout_ms=8000).click()
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


def write_stamps(fetched_months):
    """_fetched.txt(기존 호환) + _meta.json 기록 / write both stamp files."""
    now = datetime.datetime.now(KST)
    stamp = now.strftime("%Y-%m-%d")
    with open(os.path.join(CARROT, "_fetched.txt"), "w", encoding="utf-8") as f:
        f.write(stamp)

    # docs/carrot/ 전체를 스캔해 월별 일수·총계 산출 / scan the whole dir for counts
    counts = {ym: month_day_count(os.path.join(CARROT, f"{ym}.json"))
              for ym in sorted(existing_months())}
    meta = {
        "fetched_at": stamp,
        "fetched_at_iso": now.isoformat(timespec="seconds"),
        "months": list(fetched_months),
        "counts": counts,
        "total_days": sum(counts.values()),
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
        token = login_and_get_token(email, password)
    except LoginError as e:
        err(f"❌ 로그인/accesstoken 캡처 실패 / login failed: {e}")
        err("   → 비밀번호가 틀렸거나 Carrot 로그인 UI가 바뀌었을 수 있습니다.")
        err("   → Wrong password, or the Carrot login UI changed.")
        err(f"   → 덤프 확인 / check dump: {DEBUG_DIR}")
        return EXIT_LOGIN
    print("✅ accesstoken 확보 / token acquired")

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
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        saved.append(ym)
        if n == 0:
            print(f"⚠️ {ym}: 0일 — 수업이 없었거나 아직 미등록 / empty month (not an error)")
        print(f"💾 {ym}: {n}일 → docs/carrot/{ym}.json")

    if saved:
        write_stamps(saved)

    if failed:
        err(f"❌ 실패한 달 / failed months: {', '.join(failed)}")
        return EXIT_API
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

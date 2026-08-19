# 🥕 Carrot 강사 피드백 수집 복구 런북 (Recovery Runbook)

> 이 문서 하나만 따라 하면 강사 공식 피드백 자동 수집이 되살아납니다.
> Follow this runbook end-to-end to restore the weekly tutor-feedback sync.
> (작성 기준일 / as of: **2026-08-19**)

---

## 1. 무슨 일이 있었나 (What happened)

| 항목 | 내용 |
|---|---|
| 증상 / Symptom | 주간 워크플로우 `carrot-feedback.yml` 이 **2026-06-28 ~ 2026-08-16, 8주 연속 전부 실패** |
| 원인 / Root cause | GitHub repo secrets **`CARROT_EMAIL` / `CARROT_PASSWORD` 가 등록된 적이 없음** |
| 실패 지점 | `scripts/fetch_carrot_feedback.py` 가 시작하자마자 자격증명 없음으로 종료 (exit 2) |
| 피해 / Impact | `docs/carrot/` 에 `2026-06.json` 하나뿐 → **2026-07 · 2026-08 강사 피드백 전부 누락** |
| 왜 몰랐나 | `docs/carrot/_fetched.txt` 가 생성된 적 없고, `carrot.html` 은 "매주 자동 갱신됩니다" 라고만 표시 → 실패가 화면에 드러나지 않음 |

한 줄 요약(KO): **비밀번호를 저장소에 등록하지 않아서 두 달치 강사 피드백이 수집되지 않았습니다.**
One-liner (EN): The scheduled job never had credentials, so two months of tutor feedback were never fetched.

---

## 2. 복구 — 방법 A: GitHub 웹 UI (마우스만 사용)

가장 쉬운 방법입니다. 브라우저에서 진행하세요.

1. 저장소 열기 → <https://github.com/ok0327-dot/english-feedback>
2. 상단 **Settings** 탭
3. 왼쪽 사이드바 **Secrets and variables** → **Actions**
4. 초록색 **New repository secret** 버튼 → 아래 2개를 **각각** 등록

| Name (이름 — 대소문자 정확히) | Secret (값) |
|---|---|
| `CARROT_EMAIL` | `minuk-kang@sk.com` |
| `CARROT_PASSWORD` | Carrot English 로그인 비밀번호 |

5. 등록 후 **Actions** 탭 → **🎓 Carrot 강사 피드백 주간 수집** → **Run workflow**
   → `backfill` 를 `true` 로 두고 실행 (누락된 7·8월을 메꿉니다 / backfills the gap).

> 💡 Secret 은 등록 후 다시 볼 수 없습니다(쓰기 전용). 오타가 의심되면 같은 이름으로 다시 등록해 덮어쓰면 됩니다.
> Secrets are write-only; re-adding the same name overwrites it.

---

## 3. 복구 — 방법 B: 터미널 `gh` CLI (복붙 가능)

`gh` 미설치 시: <https://cli.github.com> → 설치 후 `gh auth login` 한 번.

```bash
# 1) 이메일 — 민감도 낮으므로 --body 로 바로 지정
gh secret set CARROT_EMAIL --repo ok0327-dot/english-feedback --body 'minuk-kang@sk.com'

# 2) 비밀번호 — ⚠️ --body 를 쓰지 말 것! 프롬프트로 입력해야 셸 히스토리에 남지 않음
#    (엔터 치면 입력창이 뜹니다. 값 입력 후 Enter, 그다음 Ctrl+D)
gh secret set CARROT_PASSWORD --repo ok0327-dot/english-feedback

# 3) 등록 확인 (값은 안 보이고 이름·수정시각만 표시됨 — 정상)
gh secret list --repo ok0327-dot/english-feedback
```

### 등록 직후 백필 실행 (누락 월 메우기)

```bash
# 2026-02 ~ 이번 달 중 docs/carrot/*.json 이 없는 달을 전부 수집
gh workflow run carrot-feedback.yml --repo ok0327-dot/english-feedback -f backfill=true

# 실행 상황 실시간 확인
gh run watch --repo ok0327-dot/english-feedback

# 또는 최근 실행 이력 확인
gh run list --workflow=carrot-feedback.yml --repo ok0327-dot/english-feedback --limit 5
```

성공하면 커밋 `chore(carrot): 강사 공식 피드백 주간 갱신` 이 `main` 에 푸시되고,
`docs/carrot/2026-07.json` · `2026-08.json` 과 `docs/carrot/_meta.json` 이 생깁니다.

---

## 4. 로컬에서 직접 돌려보기 (Run it locally)

Actions 를 기다리지 않고 손으로 확인하고 싶을 때.

```bash
# 준비 (최초 1회)
pip install playwright requests
python -m playwright install chromium

# 실행 — 누락 월 백필
CARROT_EMAIL='minuk-kang@sk.com' CARROT_PASSWORD='...' \
  python3 scripts/fetch_carrot_feedback.py --backfill

# 특정 월만 다시 받기
CARROT_EMAIL='...' CARROT_PASSWORD='...' \
  python3 scripts/fetch_carrot_feedback.py 2026-07 2026-08

# 백필 시작 월 바꾸기 (기본 2026-02)
... python3 scripts/fetch_carrot_feedback.py --backfill --since 2026-05

# 인자 없이 = 이번달 + 지난달 (기존 주간 동작)
... python3 scripts/fetch_carrot_feedback.py
```

> 🔐 비밀번호를 명령줄에 직접 쓰면 셸 히스토리에 남습니다.
> 명령 맨 앞에 **공백 한 칸**을 넣거나(`HISTCONTROL=ignorespace`), `.env` 에 넣고 `set -a; source .env; set +a` 로 불러오세요.
> `.env` 는 `.gitignore` 로 추적 제외됩니다. 템플릿은 저장소 루트 `.env.example`.

수집 후 페이지 재생성:

```bash
python3 scripts/build_carrot_page.py   # → docs/carrot.html 갱신
```

---

## 5. 종료 코드 표 (Exit codes) — 실패 원인 즉시 판별

`scripts/fetch_carrot_feedback.py` 는 실패 원인을 종료 코드로 구분합니다.
Actions 로그 맨 아래 `Process completed with exit code N` 을 보세요.

| 코드 | 의미 | 무엇을 확인할 것인가 (What to check) |
|:--:|---|---|
| **0** | ✅ 성공 | `docs/carrot/_meta.json` 의 `months` · `counts` 확인. 할 일 없음. |
| **2** | 🔑 자격증명 미설정 (`CARROT_EMAIL`/`CARROT_PASSWORD` 없음) **또는 잘못된 인자** (`months`/`--since` 가 `YYYY-MM` 형식이 아님) | **설정 문제.** 위 2·3장대로 Secret 등록. 이름 오타(`CAROT_`, 소문자) 주의. 로컬이면 `.env` 로드 여부 확인. 수동 실행이었다면 입력한 월 형식(`2026-07`) 확인. |
| **3** | 🚪 로그인 / accesstoken 캡처 실패 | **비밀번호가 틀렸거나 Carrot 사이트 UI 가 바뀜.** ① 브라우저로 직접 로그인해 비밀번호 확인 → 맞으면 Secret 재등록. ② 로그인은 되는데 실패하면 로그인 폼/토큰 구조 변경 → 6장 디버그 아티팩트의 스크린샷·HTML 확인. ③ 계정 잠김·CAPTCHA 여부 확인. |
| **4** | 📡 API 호출 실패 | 로그인은 성공. Carrot 서버 오류·점검·응답 형식 변경. 잠시 후 재실행(`gh workflow run ...`). 반복되면 API 응답 스키마 변경 의심 → 스크립트의 파싱부 점검. |

---

## 6. 실패 시 디버그 아티팩트 확인 (Debug artifacts)

로그인 실패(exit 3)일 때 스크립트가 화면 캡처와 페이지 HTML 을 남깁니다.

- 저장 위치: 환경변수 **`CARROT_DEBUG_DIR`** (미설정 시 저장소 루트 **`debug-carrot/`**)
- 파일: `login-failure.png` (스크린샷) · `login-failure.html` (페이지 HTML)

**GitHub Actions 에서 받는 법**

1. **Actions** 탭 → 실패한 **🎓 Carrot 강사 피드백 주간 수집** 실행 클릭
2. 실행 페이지 **맨 아래 `Artifacts` 섹션** → **`carrot-debug-<run_id>`** 다운로드 (zip)
3. 압축 풀고 `login-failure.png` 를 열어 어느 화면에서 멈췄는지 확인
   (비밀번호 오류 문구 / CAPTCHA / 점검 안내 / 폼 자체가 바뀜)

> 🔒 덤프에는 이메일·비밀번호 원문이 남지 않도록 마스킹되어 있습니다. 그래도 **`debug-carrot/` 는 `.gitignore` 로 커밋 금지**이며, zip 을 외부에 공유하지 마세요.
> Artifacts are masked, but never commit or share them.

---

## 7. 정상 동작 확인 체크리스트 (Verify)

- [ ] `gh secret list` 에 `CARROT_EMAIL` · `CARROT_PASSWORD` 둘 다 보인다
- [ ] 백필 실행이 **초록색 ✅** 로 끝났다 (`gh run list`)
      ⚠️ 시크릿이 없으면 워크플로우가 **수집을 건너뛰고도 초록**으로 끝납니다(프리플라이트 skip).
      실행 페이지 상단 Summary 에 "⚠️ … 미설정으로 건너뜀" 이 **없어야** 진짜 성공입니다.
      A skipped-for-missing-secrets run is also green — check the run Summary.
- [ ] `docs/carrot/2026-07.json` · `docs/carrot/2026-08.json` 이 생겼다
- [ ] `docs/carrot/_fetched.txt` 에 오늘 날짜(YYYY-MM-DD)가 있다
- [ ] `docs/carrot/_meta.json` 의 `months` / `counts` / `total_days` 가 채워졌다
- [ ] 사이트 <https://ok0327-dot.github.io/english-feedback/carrot.html> 에 7·8월 피드백이 보인다
- [ ] 다음 월요일 06:00 KST 자동 실행이 성공한다 (실패 시 텔레그램 알림 옴)

---

## 8. 🔐 보안 주의 (Security)

- 비밀번호를 **채팅창·이슈·커밋 메시지·코드·로그 어디에도 붙여넣지 마세요.**
  Never paste the password into chat, issues, commits, code, or logs.
- 값 전달은 **GitHub Secret** 또는 **로컬 `.env`(추적 제외)** 만 사용합니다.
- `gh secret set CARROT_PASSWORD` 는 **`--body` 없이** 실행해 프롬프트로 입력하세요(히스토리 방지).
- 이 문서에는 실제 비밀번호를 적지 않습니다. 자리표시자(`...`)만 유지하세요.
- 비밀번호를 실수로 노출했다면: Carrot 사이트에서 비밀번호 변경 → Secret 재등록.

---

## 9. 참고 파일 (Related files)

| 파일 | 역할 |
|---|---|
| `scripts/fetch_carrot_feedback.py` | 로그인 → API 수집 → `docs/carrot/*.json` · `_fetched.txt` · `_meta.json` 기록 |
| `scripts/build_carrot_page.py` | 수집된 JSON → `docs/carrot.html` 렌더링 |
| `.github/workflows/carrot-feedback.yml` | 매주 월 06:00 KST cron + 수동 실행(`months` / `backfill` 입력) |
| `.env.example` | 로컬 실행용 환경변수 템플릿 (`CARROT_EMAIL` / `CARROT_PASSWORD` 포함) |
| `docs/carrot/_meta.json` | 마지막 수집 시각·수집 월·건수 (사이트에서 신선도 표시에 사용) |

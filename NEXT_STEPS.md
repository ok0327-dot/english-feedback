# 🗺️ 다음 작업 백로그 (NEXT STEPS)

> 이어서 작업할 항목 모음. 각 항목: **무엇 / 왜 / 상태 / 방법(누가)**.
> 작업 시작할 때 이 파일을 같이 보면 맥락이 빠르게 잡힌다. (작성 기준일: 2026-08-19)

---

## ✅ 완료 (2026-08-19)

### 0. 🥕 Carrot 강사 피드백 수집 복구 — **완료**
- **무엇**: `carrot-feedback.yml` 이 **2026-06-28 ~ 2026-08-16, 8주 연속 실패**하던 것을 복구. 데이터 2월~8월 전부 수집됨.
- **원인이 2개였다**:
  1. repo secrets `CARROT_EMAIL` / `CARROT_PASSWORD` 미등록 → 즉시 exit.
  2. **`wait_until="networkidle"`** — 당근농장 사이트가 세션 리플레이 비콘
     `replays.carrotsolutions.co.kr/ingest/v1/web/start` 를 스트리밍으로 열어둔 채 끝내지 않아
     networkidle 이 **구조적으로 절대 만족될 수 없었음**(간헐 flake 아님, 100% 결정적 타임아웃).
     시크릿을 8주 전에 넣었어도 똑같이 실패했을 것.
     → `domcontentloaded` 로 변경 + 해당 비콘 `page.route` 차단으로 해결(0.4초).
- **결과**: `docs/carrot/` 2026-02~08 (7개월) · **122일 · 교정 554개** (복구 전 20일/96개).
- **재발 방지**:
  - 정기 실행이 항상 `--backfill` → 실패로 생긴 구멍을 스스로 메움.
  - 시크릿 미설정은 '실패(빨간 X)'가 아니라 **'skip + 설정 안내'** 로 구분(alert fatigue 방지).
  - 종료 코드별 텔레그램 문구(2=미설정 / 3=로그인 실패 / 4=API) + 실패 시 디버그 아티팩트 업로드.
  - `carrot.html` 에 **신선도 배너**(10일↑ 주황 / 21일↑ 빨강) + 누락 월 표시 → 수집이 죽으면 화면에서 바로 보임.
  - 커밋 스텝에 `github.ref == 'refs/heads/main'` 가드 → 브랜치 테스트가 main 을 덮어쓰지 못함.
- **참고**: 종료 코드 0=성공 / 2=시크릿 미설정·인자 오류 / 3=로그인 실패 / 4=API 실패.
  실패 시 Actions 실행 페이지 하단 **Artifacts → `carrot-debug-<run_id>`** 에 로그인 실패 스크린샷·HTML.
  상세 런북: [`scripts/CARROT_SETUP.md`](scripts/CARROT_SETUP.md).
- **⚠️ 앞으로 로그인이 깨지면**: exit 3 이 뜨고 디버그 스크린샷이 남는다. Carrot 로그인 UI 변경 또는 비밀번호 변경을 의심할 것.

---

## ✅ 완료 (2026-06-30)

### A. 📈 진척 대시보드 + 🎯 능동복습 퀴즈 — **완료**
- `scripts/build_progress.py` → `docs/progress.html`. 탭 2개: **진척**(유창성 추세선·약점 Top6·주차별 평균·통계) + **복습 퀴즈**(❌→✅/어휘 인출 카드 269장, 모드 필터, localStorage 진도). 홈에 버튼 추가.
- 매일 일일 파이프라인에서 자동 갱신($0). 금요일 루틴은 `#coach` 코칭 한마디만 통찰로 교체(보존 패턴).

### B. 📓 NotebookLM 다이제스트 — **완료**
- `scripts/build_digest.py` → `docs/digest-<주>.txt` + `docs/digest-latest.txt`. 라디오 페이지에 **"📓 다이제스트 복사" + "NotebookLM 열기"** 버튼.
- **왜**: 사용자 **Google AI Pro(NotebookLM)** 보유 → Audio Overview로 2-MC 영어 팟캐스트 무료 생성(현재 TTS보다 품질↑). 다이제스트 붙여넣기만 하면 됨.

---

### C. 🧹 데이터 품질 보강 — **완료 (2026-06-30)**
- `build_weekly_review.py` 파서 개선: ① 어휘 정규식이 번호/불릿/무접두 형식 모두 허용 → **빈 vocab 8건 → 2건**(남은 2건은 원본에 어휘 섹션 자체 없음). ② `Category:` 줄 우선 추출 + 한국어 키워드 정규화 → **약점 카테고리 한국어 혼입 제거**(12→10개 표준 카테고리). 전 JSON 재생성.
- 효과: 퀴즈 어휘 카드 92→**116장**, 다이제스트·약점 랭킹 정밀도↑.

---

## 🟢 추천 다음 단계

### 1. (남은 보강) 2건의 어휘 공백 + 깨진 페이지(2026-05-12) 정리
- **무엇**: `2026-05-20`·`2026-05-12`는 원본 HTML에 어휘 섹션이 없음(생성 단계 누락). 필요 시 해당 일자 재처리(backfill)로 보강.
- **왜**: 데이터 100% 완전성. 우선순위 낮음.

---

## 🔵 라디오/대화 기능 — 남은 Phase

요청했던 4방향 중 **A·C·B 완료**, **D 남음**.

### 2. 🗣️ Phase D — 온사이트 AI 음성 대화
- **무엇**: 사이트 라디오 페이지 안에 **채팅·음성 대화 위젯**. 내 피드백을 컨텍스트로 Gemini와 양방향 대화(+Web Speech 음성).
- **왜**: 가장 몰입감 높은 형태(복붙 없이 사이트에서 바로 대화).
- **상태**: 미착수.
- **방법**: 내가 구현(규모 큼). 기존 Cloudflare Worker 인프라(`telegram-notify-hub`)에 **Gemini 프록시 엔드포인트** 추가 → 정적 사이트에서 호출. ⚠️ 백엔드·API 키·무료 쿼터 관리 필요(=API 유료 빌링 고려).

---

## 🟡 사용자 액션만 하면 되는 것 (시크릿·실행)

### 3. 🎧 라디오 MP3 첫 생성
- **상태**: Phase B 인프라 완비. 첫 MP3만 안 만들어짐.
- **방법(사용자)**: GitHub → Actions → **"🎧 주간 라디오 오디오"** → **Run workflow**. 기존 `GEMINI_API_KEY` 사용. 안 돌려도 **다음 금요일 17:00 KST 자동**.
- **참고**: Gemini TTS는 무료 쿼터 밖일 수 있음(~18분 주1회 소액). 실패 시 gTTS 폴백(무료)이 자동 처리.

### 5. 📱 텔레그램에 음성 파일 그대로 받기 (선택)
- **상태**: 현재는 허브로 **링크** 발송. 네이티브 음성도 코드상 지원됨.
- **방법(사용자)**: Secret 2개 추가 → `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. 있으면 radio-audio 워크플로우가 음성 파일을 채팅에 바로 발송.

---

## 🧭 현재 시스템 한눈에 (참고)
- **매일(평일)**: `english-feedback.yml` → `process_lesson.py`(Drive 녹음→Groq 전사→Gemini 피드백→docs/일일 페이지+이메일). 짤림 방지 패치 적용됨.
- **매주 금(클라우드 Claude 루틴 `trig_01U9s2QgDnVTFKarpV5PfFo4`)**: 짤린 일일 자가복구 → 주간 복습(`build_weekly_review`) → synthesis/curation/강사vsAI/라디오 대본(`#radio-src`, 15~20분 전부영어 Topic Talk) 교체 → 푸시. 정본 = `scripts/WEEKLY_ROUTINE.md`.
- **매주 월**: `carrot-feedback.yml` 강사 피드백 수집 — ✅ 정상(2026-08-19 복구). 정기 실행도 `--backfill` 이라 구멍이 생기면 스스로 메움. 런북 `scripts/CARROT_SETUP.md`.
- **매주 금(루틴 직후)**: `radio-audio.yml` 라디오 MP3 생성(Gemini TTS→폴백 gTTS)+텔레그램.
- **페이지**: 일일 홈(index) → 주간 복습 / 🎓 강사 공식 피드백 / 🎙️ 영어 주간 라디오.

# 🗺️ 다음 작업 백로그 (NEXT STEPS)

> 이어서 작업할 항목 모음. 각 항목: **무엇 / 왜 / 상태 / 방법(누가)**.
> 작업 시작할 때 이 파일을 같이 보면 맥락이 빠르게 잡힌다. (작성 기준일: 2026-06-26)

---

## 🟢 추천 다음 단계

### 1. 📓 NotebookLM 다이제스트 (구독 활용 · 추천)
- **무엇**: 매주 "그 주 교정·표현·문법·주제·어휘"를 한 장 텍스트/파일(`docs/digest-YYYY-Www.txt` 등)로 자동 생성하고, 라디오 페이지에 **"📓 NotebookLM용 복사" 버튼** 추가.
- **왜**: 사용자가 **Gemini 유료 구독(Google AI Pro)** 보유. 구독은 API엔 도움 안 되지만 **NotebookLM Audio Overview**(2-MC 팟캐스트 자동 생성, 매우 자연스러움, 비용 0)엔 강력. 다이제스트를 NotebookLM에 붙여넣으면 고품질 영어 팟캐스트를 직접 뽑을 수 있음 → 현재 TTS보다 품질↑.
- **상태**: 미착수(제안만).
- **방법**: 내가 구현. `scripts/build_digest.py`(build_weekly_review 파싱 재사용) + radio.html 버튼. 금요일 루틴에 한 줄 추가. 무료 TTS/MP3 경로는 폴백으로 유지.

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

### 4. 🥕 강사 피드백 주간 자동 수집 켜기
- **상태**: 코드·워크플로우 완비. 현재 페이지·이번 달 데이터는 이미 라이브. **다음 주부터 자동 갱신**만 미설정.
- **방법(사용자)**: 레포 → Settings → Secrets and variables → Actions → **New repository secret** 2개:
  - `CARROT_EMAIL` = `minuk-kang@sk.com`
  - `CARROT_PASSWORD` = (Carrot 비밀번호)
- 추가 후 Actions → "🎓 Carrot 강사 피드백 주간 수집" → Run workflow로 즉시 테스트 가능.

### 5. 📱 텔레그램에 음성 파일 그대로 받기 (선택)
- **상태**: 현재는 허브로 **링크** 발송. 네이티브 음성도 코드상 지원됨.
- **방법(사용자)**: Secret 2개 추가 → `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. 있으면 radio-audio 워크플로우가 음성 파일을 채팅에 바로 발송.

---

## 🧭 현재 시스템 한눈에 (참고)
- **매일(평일)**: `english-feedback.yml` → `process_lesson.py`(Drive 녹음→Groq 전사→Gemini 피드백→docs/일일 페이지+이메일). 짤림 방지 패치 적용됨.
- **매주 금(클라우드 Claude 루틴 `trig_01U9s2QgDnVTFKarpV5PfFo4`)**: 짤린 일일 자가복구 → 주간 복습(`build_weekly_review`) → synthesis/curation/강사vsAI/라디오 대본(`#radio-src`, 15~20분 전부영어 Topic Talk) 교체 → 푸시. 정본 = `scripts/WEEKLY_ROUTINE.md`.
- **매주 월**: `carrot-feedback.yml` 강사 피드백 수집(시크릿 필요 — 위 4번).
- **매주 금(루틴 직후)**: `radio-audio.yml` 라디오 MP3 생성(Gemini TTS→폴백 gTTS)+텔레그램.
- **페이지**: 일일 홈(index) → 주간 복습 / 🎓 강사 공식 피드백 / 🎙️ 영어 주간 라디오.

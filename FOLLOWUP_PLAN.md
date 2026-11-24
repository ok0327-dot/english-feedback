# 💬 후속 대화 계획 (FOLLOWUP_PLAN)

> 매일 피드백을 읽은 뒤 **(a) 그날 수업에 대해 한국어로 묻기** 또는 **(b) 그날 대화를 이어 AI와 영어로 더 말하기**.
> 작성 2026-11-24 · 상태: **계획 (미착수)** · Claude 초안 → Codex 독립 검토 1회 반영 (7절)

---

## 0. 한 줄 결론

**"그날 전사 + 피드백 전체를 새 대화에 넣는다"는 방향은 맞다** (하루 6~8천 토큰이라 어느 앱에나 통째로 들어간다).
바꿀 점은 두 가지다.
1. **대화를 이어갈 곳은 Codex보다 ChatGPT 앱과 Gemini 앱이 낫다** (근거 3절).
2. **프롬프트(무엇을 넣을지)와 대화할 앱(어디서 할지)을 분리한다.** 프롬프트는 한 곳에서 만들고, 어느 앱이든 같은 내용을 받는다.

---

## 1. 지금 있는 것 (저장소에서 확인한 사실)

| 항목 | 사실 | 위치 |
|---|---|---|
| 이미 있는 버튼 | 매일 페이지의 **"Gemini에서 복습 대화 시작하기"**: 전사 전체 + 피드백 전체 + 연습 지시를 클립보드에 복사한 뒤, 600ms 뒤에 gemini.google.com을 연다 | `process_lesson.py:1342-1359`, `:1443` |
| 낡은 지시 | 그 프롬프트가 지금 피드백에는 없는 "반복 실수 패턴" 섹션을 가리킨다 | `process_lesson.py:1353` |
| 고정 삽입 | 프롬프트가 각 페이지 HTML에 문자열로 박혀 있어서, 템플릿을 고쳐도 과거 페이지는 바뀌지 않는다 | 153개 페이지 전부 `const REVIEW_PROMPT=` |
| 하루 분량 | 전사 1.1~1.5만 자 + 피드백 6~7천 자 ≈ **6~8k 토큰** | 11-18~11-24 실측 |
| 구조화 데이터 | `docs/data/<날짜>.json`: topic · grammar_norm · score · pairs(❌/✅ 약 5개) · vocab. 전사는 없다 | `scripts/build_weekly_review.py:65` |
| 강사 교정 | `docs/carrot/YYYY-MM.json`. **주 1회(월)** 수집이라 그날 페이지를 만들 때는 보통 아직 없다 | `.github/workflows/carrot-feedback.yml:11` |
| 비슷한 패턴 | 라디오 페이지의 `PROMPTS={chat,lecture,radio}` + `copyOpen(mode)` | `scripts/build_radio.py:1249`, `:1408-1411` |
| 학습자 기록 | 브라우저 localStorage(`efb_quiz_v1`)에만 남고, 서버로 되돌아오는 길은 없다 | `scripts/build_progress.py:309-311` |
| 남은 백로그 | "Phase D — 사이트 안 AI 음성 대화" 미착수 | `NEXT_STEPS.md:70-75` |
| 공개 범위 | 저장소와 Pages가 **공개**다. 전사에 가족·직장 정보가 이미 노출돼 있다 | 6절 D1 |

---

## 2. 설계: 프롬프트와 대화할 앱을 분리한다

```
            ┌─ 💬 이어서 대화하기 (페이지 안) ─┐
 그날 전사 ─┤  모드 ① 한국어 질문            ├─ 복사 ─→ Gemini 앱   (→ Live 음성)
 그날 피드백┤  모드 ② 영어 대화 (음성용)     │         ChatGPT 앱  (→ 프로젝트 + 음성)
 최근 교정 ─┤  모드 ③ 약점 집중 연습         │         Claude 앱
 (강사 교정)┘  공통: "정리" → 고정 양식 정리  ┘         PC: room1 (Claude Code)
                         │
                         └─ 정리 블록 → 복습 퀴즈로 되돌려 넣기 (3단계)
```

- 프롬프트 템플릿은 `docs/followup.js` **한 곳**에서만 관리한다. 템플릿을 고칠 때 페이지를 다시 만들 필요가 없다.
- 앱마다 프롬프트를 따로 만들지 않는다. 앱이 바뀌어도(12월 변화, 6절) 내용 쪽은 그대로 둔다.

---

## 3. 어디서 대화할까 (2026-11 기준)

| 통로 | 한국어 질문 | 영어 음성 대화 | 지금 바로 | 판단 |
|---|---|---|---|---|
| **Gemini 앱** (Google AI Pro) | ✅ | ✅ 글로 붙여넣은 대화를 **같은 대화창에서 Live 음성으로 전환** | ✅ 기존 버튼 | **주 통로 후보 1** |
| **ChatGPT 앱 + 프로젝트** (Plus) | ✅ | ✅ 프로젝트 안 음성(GPT-Live)이 프로젝트 지시문·파일을 쓴다 (웹 조사) | 프로젝트 한 번 만들면 ✅ | **주 통로 후보 2** |
| Claude 앱 | ✅ | △ 음성 모드 베타. 매일 파이프라인과 **같은 구독 한도**를 쓴다 | ✅ | 한국어 질문용 보조 |
| room1 (폰 Claude 앱 → PC Claude Code) | ✅ 로컬 페이지를 직접 읽음 | ✕ (받아쓰기만 됨) | ✅ 코드 0줄 | PC가 켜져 있을 때 한국어 질문용 |
| **Codex** (사용자 원안) | ✅ | △ 음성은 PC 앱과 페어링해야 함. codex-voice는 지금 끊겨 있음 | 붙여넣기로 ✅ | **주 통로로는 비추천** ↓ |
| 사이트 안 음성 위젯 | ✅ | ✅ | ✕ (규모 큼) | 4단계, 보류 |

**Codex를 주 통로로 쓰지 않는 이유**
- Codex는 코딩 에이전트(coding agent)다. 같은 Plus 구독의 **ChatGPT 앱이 같은 음성 모델(GPT-Live)을 대화용으로 더 잘 쓴다.**
- **12월부터 Plus에서 ChatGPT와 Codex가 사용량을 함께 쓴다** (웹 조사, 출처: help.openai.com/en/articles/20001625). Codex로 영어 대화를 하면 코딩과 `/codex` 검토에 쓸 한도가 줄어든다.
- codex-voice는 11-20 Windows 설정(`runCodexInWindowsSubsystemForLinux=false`)이 바뀐 뒤 WSL 스킬 경로가 끊긴 상태다.
- 단, **PC에서 저장소 작업을 같이 할 때**(예: 정리 결과를 파일로 저장)는 Codex나 Claude Code가 낫다 → 2-3.

**음성 대화 앱은 Gemini와 ChatGPT를 1주씩 써 보고 고른다.** 둘 다 일반 대화 상대로는 좋지만, **발음을 믿을 만하게 채점해 주는 일반 AI 앱은 없다** (웹 조사). 발음 교정은 기대하지 않는다.

---

## 4. 단계별 계획

### 0단계 — 오늘부터, 코드 0줄
- **영어 음성**: 기존 "Gemini에서 복습 대화" 버튼 → 붙여넣기 → 같은 대화에서 **Live(음성) 버튼**으로 전환. 첫 메시지 뒤에 5절의 모드 ② 지시를 덧붙여도 된다.
- **한국어 질문**: PC가 켜져 있으면 폰 Claude 앱 room1에서 "오늘 영어 수업 페이지 읽고 한국어로 질문 받아줘". 아니면 버튼으로 복사한 내용을 아무 앱에나 붙여넣고 5절 모드 ① 지시를 덧붙인다.
- **ChatGPT 시험**: 프로젝트 "English follow-up"을 만들고 5절 지시문을 프로젝트 지시(instructions)에 넣는다 → 그날 내용을 붙여넣기 → 음성.

### 1단계 — "💬 이어서 대화하기" 만들기 (반나절~1일)
| # | 할 일 | 비고 |
|---|---|---|
| 1-1 | `docs/followup.js`(공용 스크립트) + `docs/followup.html?d=YYYY-MM-DD`(**모든 날짜용 페이지 하나**) | 프롬프트 템플릿은 여기에만 둔다 |
| 1-2 | **데이터를 가져오는 규칙**: 새 페이지는 `<script type="application/json" id="lesson-data">`에 {date, topic, transcript, feedback_md}를 넣는다. 과거 페이지는 HTML을 받아 `const REVIEW_PROMPT=` 문자열을 `[오늘 수업 전사 내용]` / `[AI 피드백]` / `위 내용을 바탕으로` 표지로 자른다 (**153개 전부 표지 확인**). 표지를 못 찾으면 REVIEW_PROMPT 전체를 그대로 쓰고 경고를 띄운다 | 화면에 그려진 HTML(DOM)은 읽지 않는다 → 7절 #4 |
| 1-3 | **과거 153개 HTML은 수정하지 않는다** | 수정하면 `_html_md5`(파일 지문)가 바뀌어 153개 `docs/data/*.json`이 지금 파서로 조용히 다시 만들어진다 (`scripts/build_weekly_review.py:124-138`) → 7절 #5 |
| 1-4 | 모드 3개(5절): ① 한국어 질문 ② 영어 대화(음성용) ③ 약점 집중 연습(기존 드릴 개선). 공통 "정리" 양식 | 쉬운 말 문법 원칙(`PLAIN_GRAMMAR_RULE`)을 따른다 |
| 1-5 | 덧붙일 내용: **최근 5회 수업의 ✅ 표현 몇 개**(`docs/data` pairs) → "오늘 섞어 써 볼 표현". 강사 교정은 그 날짜 것이 있으면 넣는다 | 반복 약점을 "찾아내는" 기능이 아니라 **최근 교정을 다시 써 보는 것**이다 → 7절 #3 |
| 1-6 | **버튼 흐름**: 페이지가 열릴 때 프롬프트를 미리 만들어 둔다 → [모드] 탭 = 복사 → 그 자리에 **앱 링크 3개(`<a href>`)를 보여 주고 사용자가 직접 탭**한다. 복사에 실패하면 전문이 든 텍스트 칸을 펼친다 | 지금의 "600ms 뒤 `window.open`"은 폰에서 팝업 차단될 수 있다 → 7절 #6 |
| 1-7 | **사용 기록**: localStorage `efb_followup_v1`에 날짜·모드·앱을 남기고, progress 페이지에 "이번 주 후속 대화 N회"를 표시한다 | 어느 앱을 실제로 쓰는지 기억에 맡기지 않는다 → 7절 #7 |
| 1-8 | `process_lesson.py`: 새 페이지는 REVIEW_PROMPT 대신 lesson-data 블록 + followup.js를 넣는다. 버튼 문구는 "💬 이어서 대화하기". 낡은 "반복 실수 패턴" 지시는 지운다 | 기존 Gemini 버튼은 과거 페이지에 그대로 남는다 |

**검증**
- (a) 자동 테스트: 과거 153개 페이지 전부에서 추출이 성공하는지, 모드별 프롬프트 길이가 범위 안인지.
- (b) Playwright: 최근 페이지에서 모드마다 복사 내용에 전사·피드백·모드 지시가 들어가는지.
- (c) **실제 폰 점검표** (Android Chrome + 설치된 PWA, 가능하면 iOS): 복사 → 앱 열기 → 붙여넣기 → 음성 전환을 앱마다 3회씩.

### 2단계 — 붙여넣기 줄이기
- **2-1 ChatGPT 프로젝트 지시문 고정**: 5절 규칙을 프로젝트 지시에 한 번만 넣고, 매일은 데이터만 붙여넣는다. *미확인: 프로젝트 안 음성이 지시문을 실제로 따르는지 → 직접 1회 확인.*
- **2-2 (실험) Google 문서 하나 자동 갱신**: 사용자가 한 번 만든 Google 문서를 파이프라인이 매일 그날 내용으로 덮어쓴다. Gemini skill과 Gemini Notebook(옛 NotebookLM)이 Drive 문서를 자동으로 다시 읽으므로, 한국어 질문은 붙여넣기 없이 할 수 있다.
  - *미확인*: 서비스 계정이 Google 문서 본문을 덮어쓸 수 있는가. 지금 선례는 jsonl 파일에 **덧붙이기**뿐이다(`process_lesson.py:516-540`).
  - 이 문서는 `docs/`의 복사본이라 망가져도 다시 만들 수 있다. Google 문서의 버전 기록도 남는다.
  - Live 음성은 skill을 못 보므로 **음성은 여전히 붙여넣기 경로**다.
- **2-3 PC 통로**: Claude Code 스킬 `english-tutor` → room1에서 "오늘 수업 이어서" 한마디면 된다. codex-voice는 Windows 설정을 되돌리는 일이 먼저이고, 별도 과제로 둔다.

### 3단계 — 되돌려 넣기 (대화 결과 → 복습)
- **3-1** 고정 정리 양식(5절) → followup 페이지의 "정리 붙여넣기" 칸 → 파서 → localStorage `efb_followup_cards_v1` → progress 퀴즈가 빌드 때 만든 카드와 이 카드를 합쳐 보여 준다.
  - **새로 만들어야 할 것**: 파서, 중복 제거, 카드 합치기 (지금 퀴즈 카드는 빌드 때 HTML에 박힌다, `scripts/build_progress.py:301-308`).
  - 기기 한 대에서만 보인다.
- **3-2** 다른 기기에서도 보거나 라디오에 반영하려면: 텔레그램 캡쳐방에 "#영어정리" 메모 → 주간 루틴이 모아서 → 금요일 라디오·주간 복습에 반영. 허브와 주간 스크립트를 고쳐야 한다 (중간 규모).
- **3-3 효과 측정**: 다음 수업들에서 같은 `grammar_norm`이 다시 나오는 비율, 정리 카드 퀴즈 정답률.

### 4단계 — 사이트 안 음성 대화 (보류)
`NEXT_STEPS.md` Phase D. **열기 조건**: 1~3단계를 하고도 "붙여넣기가 귀찮아서 안 한다"가 사용 기록(1-7)으로 확인될 때. 열 때는 운영 조건을 먼저 정한다.
- 사용자 인증
- 호출 상한(rate limit)
- API 키(데이터 출입증)는 Cloudflare Worker 안에만 둔다
- 음성·전사를 서버에 남기지 않는다
- Gemini API 무료 등급은 입력을 제품 개선에 쓴다(웹 조사) → 개인 전사라면 유료 등급을 검토한다 (Live 음성 약 $0.02/분, 웹 조사)
- 장애가 나면 복사 버튼으로 대체한다

---

## 5. 프롬프트 초안 (1단계 템플릿의 출발점 · 0단계에 바로 붙여 써도 됨)

**모드 ① 한국어 질문**
```
너는 내 전화영어 수업 기록을 같이 보는 영어 코치야. 아래 [수업 전사]와 [피드백]은 오늘 수업 기록이야.
- 내가 한국어로 물으면 한국어로 답해. 영어 예문은 영어로 써.
- 문법책 용어(과거분사, to부정사 같은 것) 대신 소리·덩어리·느낌으로 설명해. 꼭 필요하면 쉬운 설명 뒤 괄호에 한 번만.
- 답할 때 전사에서 내가 실제로 한 말을 짧게 인용하고, 그 상황에서 원어민이 쓸 표현 2~3개를 격식 차이와 함께 보여 줘.
- 기록에 없는 내용은 지어내지 마. 기록에서 확인이 안 되면 "기록엔 없어"라고 말해.
- 첫 답: "오늘 수업 기록 확인했어요" + 내가 물어볼 만한 질문 3개를 제안하고, 내 질문을 기다려.
```

**모드 ② 영어 대화 (음성용)**
```
You are my English conversation partner. Below is today's phone-English lesson (transcript + feedback).
Continue the conversation on the same topics, as if the lesson kept going.
- Short turns: 1–2 sentences, then one question. No lists, symbols, or markdown — this will be spoken aloud.
- Naturally reuse the corrected expressions (✅) and vocabulary from the feedback, and nudge me to use them too.
- When I make a mistake, don't stop the flow: say my sentence back the natural way and keep going. Keep a silent list.
- English only. Switch to Korean only if I say "한국어로".
- When I say "wrap up" or "정리", stop and give the summary in the exact format below.
- Start with one question that continues today's main topic.
```

**공통 정리 양식** (3단계 파서가 읽는 형식 — 바꾸지 않는다)
```
[정리 YYYY-MM-DD]
❌ 내가 한 말 → ✅ 자연스러운 말
💬 유용한 표현 — 한국어 뜻
```

---

## 6. 위험 · 미확인 · 사용자 결정

| # | 내용 | 결정/조치 |
|---|---|---|
| D1 | **개인정보**: 공개 페이지에 가족·직장 정보와 녹음 파일명의 숫자가 이미 노출돼 있다. 후속 대화로 앱에 보내도 노출이 크게 늘지는 않지만, 공개 노출 자체는 이 계획과 별개로 정할 일이다 | **사용자 결정** (별도 과제). 각 앱의 "대화를 학습에 사용" 설정을 확인할 것을 권장 |
| D2 | 주 음성 앱: Gemini냐 ChatGPT냐 | 1단계 사용 기록으로 1주 뒤 결정 |
| D3 | Codex는 PC에서 저장소 작업을 같이 할 때만 쓴다 | 권장 |
| R1 | **12월 일정**: ChatGPT 옛 음성 모드 12-11 종료(GPT-Live로 교체) · Plus ChatGPT/Codex 사용량 통합(12월) · **Gems 12-17 삭제**(Gemini skill로 이전) → Gem에 기대는 설계는 하지 않는다 | 반영됨 |
| R2 | NotebookLM → **Gemini Notebook** 이름 변경(2026-07) → 라디오 페이지의 "NotebookLM 열기" 문구를 갱신해야 한다 | 작은 일, 1단계 때 같이 |
| R3 | Claude 앱 음성은 매일 피드백 파이프라인(Claude opus, 하루 약 70.8k 토큰)과 **같은 구독 한도**를 쓴다 | 많이 쓰면 주의 |
| R4 | 웹 조사 결과는 출처가 있지만 Claude가 원문을 직접 열어 보지 않은 것이 많다 → 각 단계에서 쓰기 전에 실제 앱으로 1회 확인한다 | — |

---

## 7. Codex 독립 검토 반영 기록 (2026-11-24, 계획 비판 1회)

지적 10 / **확인됨 6** / **반증됨 1** / **미확인 3**

| # | Codex 지적 | 판정 | 반영 |
|---|---|---|---|
| 1 | 공개 전사를 외부 AI로 보내는 위험이 빠짐 | 확인됨 (공개는 사실이고, 결정 기록이 없음) | 6절 D1 |
| 2 | PWA 캐시 때문에 새 스크립트가 안 퍼질 수 있음 | **반증됨**: `docs/sw.js:2,11-24`가 network-first라 온라인에서는 항상 최신 | 버림 (오프라인에서만 옛 사본) |
| 3 | `docs/data`만으로는 반복 약점을 못 묶음 | 확인됨 (grammar_norm 빈도 + pairs 5개뿐) | 1-5를 "최근 교정 다시 쓰기"로 낮춤 |
| 4 | 화면 HTML에서 다시 조립하는 규칙이 없음 | 확인됨 | 1-2: REVIEW_PROMPT 표지 추출(153/153) + 새 페이지 JSON 블록 |
| 5 | 과거 153개 일괄 수정의 위험 | 확인됨 + **`_html_md5` 때문에 JSON 153개가 다시 만들어지는 부작용** 추가 발견 | 1-3: 과거 HTML은 수정하지 않음 |
| 6 | 폰에서 복사·앱 열기가 실패할 수 있음 | 미확인 (실제 기기가 필요) | 1-6 직접 탭 링크 + 검증 (c) 폰 점검표 |
| 7 | 1주 관찰을 잴 방법이 없음 | 확인됨 | 1-7 사용 기록 |
| 8 | Google 문서 덮어쓰기는 선례와 다르고 되돌리기 어려움 | 미확인 (가능 여부) / 되돌리기 위험은 낮음 (다시 만들 수 있는 복사본) | 2-2를 "실험"으로 표시 |
| 9 | 정리 블록 → 퀴즈 연결부가 없음 | 확인됨 | 3-1에 새로 만들 것을 명시 |
| 10 | 4단계 Worker에 인증·비용·보관 정책이 없음 | 미확인 (미래 설계) | 4단계 열기 조건에 추가 |

---

## 부록 — 웹 조사 출처 (2026-11-24 검색)
- ChatGPT 프로젝트 / 음성(GPT-Live)이 프로젝트를 지원: help.openai.com/en/articles/10169521 · 릴리스 노트 help.openai.com/en/articles/6825453 (2026-08-07)
- Plus ChatGPT·Codex 사용량 통합: help.openai.com/en/articles/20001625
- ChatGPT 음성 FAQ (한도·발음 기능): help.openai.com/en/articles/20001274
- Claude 주소 미리채우기 `?q=` (~14,000자): support.claude.com/en/articles/14729294 · 음성 모드: support.claude.com/en/articles/11101966
- Gemini skill에 Drive 파일 추가 (자동 갱신): workspaceupdates.googleblog.com (2026-11) · Gems와 Live: support.google.com/gemini/answer/15146780
- Gemini Notebook Drive 자동 동기화: workspaceupdates.googleblog.com (2026-05)
- Gemini API 가격·데이터 사용: aistudio.google.com/docs/pricing
- Cloudflare URL 16KB 제한: developers.cloudflare.com/fundamentals/reference/connection-limits/

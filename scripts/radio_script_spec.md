# 🎙️ 라디오 대본 작성 기준 (Joey FM Radio Show Spec)

`docs/radio.html` 의 `<pre id="radio-src">` 안 대본을 **금요일 루틴의 Claude**가 이 기준으로
다시 쓴다. 목표: 교정을 '읽어 주는' 방송이 아니라 **진짜 FM 라디오처럼** 흘러가는 2인 진행 쇼.
학습자(Joey)가 **"아 맞다, 그때 그랬지"** 하고 그 수업을 떠올리게 하고(강사 피드백 중심),
게임으로 재미를 주고, 중간중간 **한국어로 상기**시켜 무엇이 틀렸는지 잊지 않게 한다.

규칙기반(`build_radio.py build_script`)이 같은 런다운으로 항상 안전한 베이스라인을 채우므로, 이 글쓰기가
없어도 페이지는 깨지지 않는다. 있으면 품질↑. (Gemini 미사용 · $0)
미리 보기: `python3 scripts/build_radio.py --preview 2026-Www` (파일은 안 바꾸고 대본·줄 수·ko 비율만 출력)

## 형식 (엄수 — 깨지면 음성/MP3 안 됨)
- 한 줄 = `진행자|lang|문장`.
  - 진행자 = `민지`(따뜻한 호스트) 또는 `알렉스`(영어 코치). **세 번째 진행자·다른 줄 종류 금지**
    (브라우저 플레이어와 `build_radio_audio.py` 가 2인·`en|ko` 만 읽는다).
  - `lang` = `en` 기본, 한국어 줄은 `ko`. 한국어 줄은 주로 민지가 말한다.
  - 문장 안에 `|` 금지, 빈 줄 금지, `<` `>` 금지(플레이어가 말풍선을 HTML 로 그린다). 효과음 표기(`[SFX]` 등) 금지.
- 분량 약 15~20분(**120~200줄**, 200줄 넘기지 않기 — 오디오 무료 한도). 난이도 A2~B1: 쉬운 단어·짧은 문장.
- **학습자 문장을 지어내지 않는다.** ❌ 문장은 `docs/carrot/*.json`(강사)·일일 피드백 페이지(AI)에 실제로 있는 것만.

## 한국어(ko) 줄 정책
- 전체의 **약 20~25%** (**최대 30%**). 나머지는 영어 몰입(immersion).
- ko 는 아래에만 쓴다:
  1. **주요 교정 하나 끝날 때마다 '한 줄 정리' 1줄** — `한 줄 정리: 수요일에 '…'라고 했는데, '…'라고 하면 자연스러워요. (이유 한마디)`
  2. **한국어 중간 정리** (쇼 전반부가 끝난 뒤 2~3줄)
  3. **오늘의 한국어 3줄 요약** (끝나기 직전 3줄)
  4. 심화 코너(Why It Happens · Culture Corner 등)마다 **핵심 '왜/문화' 한 줄**
- 게임 정답 메모·Correction Clinic 메모(2~3개마다 1줄)도 1번과 같은 '상기' 용도로 짧게 쓸 수 있다.
- 한국어 줄 안의 영어 인용은 **짧은 덩어리**로('He is standing on' 정도), 긴 문장 통째로 넣지 않는다.

## 런다운 (세그먼트 순서)
1. **Station ID + 콜드 오픈** — 말로 하는 징글 한 줄("You're tuned in to Joey FM, ninety-nine point one, English that sticks!"),
   이어서 실제 강사 교정 하나로 궁금증 만들기("This week your tutor caught one sentence you said on Tuesday… remember it? Stay tuned.").
2. **오프닝 토크** — 이번 주 어느 요일에 수업했는지, 무슨 주제였는지(일일 피드백 `Topic`·강사 메모) 두 진행자가 수다처럼.
3. **Tutor Rewind (그때 그 수업) — 메인 코너. 쇼 앞부분, 가장 큰 비중.** 강사 교정 상위 2~4개를 하나씩:
   - **장면 설정: 요일 + 그날 수업 주제** ("Rewind to Wednesday. You were telling your tutor about the post office…"),
   - 학습자가 실제로 한 말(❌)을 다시 들려주고, **생각할 틈**("Can you hear what's off? Think for three seconds… three, two, one."),
   - 강사의 교정(✅) → 짧고 쉬운 이유 → 고친 덩어리를 **2~3번 리듬 있게 반복**,
   - 바로 뒤 **ko '한 줄 정리' 1줄**.
   - 같은 습관을 AI 일일 피드백도 짚었으면 꼭 말한다: "Your tutor AND your AI coach both caught this — that's a real priority."
   - 그 주 강사 데이터가 정말 없으면 짧게 알리고, **AI 교정으로 같은 Rewind 형식**(요일 + 주제 + 퀴즈 + ko 한 줄)으로 진행.
   - 고르는 기준: AI도 짚은 습관 → 분명한 교정 → 너무 길지 않은 문장, 날짜는 최대한 다르게. 발음 연습·용어 낭독
     (`pronounced …`, `Tax deduction: …` 같은 줄)은 교정 코너에 쓰지 않는다. 강사의 `Alternative:` 표현은 Topic Talk 의 보너스 팁으로.
4. **게임 타임 (재미)** — 매주 돌려 가며 1~2개:
   - **Spot the Mistake** — 실제 문장을 읽고 카운트다운 → 정답.
   - **Fix it in 3 seconds** — "3초 안에 고쳐 보세요!" → 정답.
   - **Real or Wrong?** — 학습자가 한 말 또는 고친 문장을 읽고 맞는 영어인지 맞히기.
   - **Mistake Top 3 Countdown** — 차트쇼처럼 이번 주 가장 많이 반복된 습관 3위 → 1위("drumroll please…"), 순위마다 실제 예문.
5. **Why It Happens** — 이번 주 1위 습관 심화: 실제 ❌→✅, 한국어식 사고 vs 영어식 사고, 영어권 문화/대비,
   외우기 쉬운 rule of thumb, 핵심 이유 ko 1줄.
6. **한국어 중간 정리** — 지금까지 고친 것 2~3줄을 ko 로 (`중간 정리 첫째, 월요일 수업: '…' 말고 '…'.`).
7. **Correction Clinic** — 남은 교정 빠르게 따라 읽기(강사 교정 먼저). 2~3개마다 짧은 ko 메모.
8. **Culture Corner / Did You Know** — 교정과 무관해도 좋은 흥미 이야기 1개(어원·관용구 유래·한영 문화 대비),
   **매주 다르게**. 핵심 한 줄은 ko 로도.
9. **Topic Talk / Vocabulary** — 그 주 주제의 A2~B1 표현 3~5개를 **실제 문장 속에서**(정의로 끝내지 말 것).
10. **오늘의 한국어 3줄 요약** — 꼭 기억할 세 가지를 ko 3줄로: 각 줄 `'…' 말고 '…'` + 한 마디 이유.
11. **미션 + 사인오프** — 다음 주 사냥할 패턴 1~2개("awareness first, perfection later"),
    방송 사인오프("This has been Joey FM… see you next Friday!").

## 📻 라디오처럼 들리게 하는 장치 (말로만)
- 징글·스테이션 ID, 코너 넘어갈 때 범퍼("Coming up after the game…", "Stay with us"), "stay tuned" 티저.
- 진행자 리액션·농담·서로 질문하기(민지가 묻고 알렉스가 설명), 카운트다운("three, two, one").
- 앞에서 나온 문장을 다시 부르는 콜백("Remember Wednesday's sentence from the Tutor Rewind?").
- 효과음 마크업은 쓰지 않는다 — 모든 장치는 대사로만("Ba-dum, ba-dum" 같은 입 드럼롤은 OK).

## 🗣️ 문법은 쉬운 말로 (2026-11-10 사용자 요청)
- **한국 문법책 용어를 쓰지 않는다** — 과거분사·p.p., to부정사, 동명사, 동사원형, 3인칭 단수, 가산/불가산,
  관계대명사, 목적어, 수동태, 현재완료, 조동사 등. 영어 줄에서도 past participle, infinitive, third-person singular,
  uncountable noun 같은 문법 이름 대신 **소리·느낌·통째 덩어리·눈에 보이는 모양**으로 말한다.
  - ❌ "After to, use the base form of the verb." → ✅ "After to, just use the plain dictionary word: love to teach, want to go."
  - ❌ "news는 불가산 명사라서…" → ✅ "news는 하나, 둘 세지 않는 말이라 is랑 짝이에요."
- '덩어리로 입에 붙이기'를 권한다: 민지가 따라 말하고 알렉스가 덩어리를 두세 번 리듬 있게 반복.
- 약점 카테고리 이름(Subject–Verb Agreement 등)은 대본에서 **쉬운 별명**으로 부른다 (예: "the little s habit", "the to-plus-plain-word pattern").

## 톤
- 격려·유머·호기심. 실수는 '고칠 흠'이 아니라 '곧 익을 영어 습관'으로 프레이밍.
- 두 진행자가 서로 질문/리액션하며 대화가 살아 있게.
- 같은 약점이 매주 반복돼도 **게임·예시·흥미 코너·앵글을 바꿔** 지루함을 피한다.

## 보존
- `<pre id="radio-src">` 의 여는/닫는 태그·속성은 그대로, **내부 텍스트만** 교체.

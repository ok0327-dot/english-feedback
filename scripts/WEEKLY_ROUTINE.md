# 📅 주간 복습 클라우드 루틴 (금요일) — 프롬프트 정본

> 이 파일은 claude.ai `/schedule` 루틴(`trig_01U9s2QgDnVTFKarpV5PfFo4`, 매주 금 15:30 KST,
> sonnet-4-6)의 **프롬프트 정본**이다. 루틴 프롬프트를 바꾸려면 이 파일을 고치고,
> claude.ai 루틴 편집 화면에 그대로 붙여넣어 동기화한다(루틴 프롬프트는 클라우드에만 저장됨).

## 루틴이 하는 일 (요약)
1. **짤린 일일 페이지 자가복구**. Claude가 직접 보강.
2. 주간 복습 스냅샷 재생성(`build_weekly_review.py`).
3. 현재 주 종합문(`#synthesis`) + 누적 큐레이션(`#curation`) + **강사vsAI 비교(`#carrot_compare`)**를 Claude 통찰로 교체.
4. **주간 라디오 대본 생성·업그레이드**(`build_radio.py` + `#radio-src` 담화 교체).
5. **진척 대시보드/퀴즈 + NotebookLM 다이제스트 재생성**(`build_progress.py`/`build_digest.py`) + 진척 코칭(`#coach`) Claude 교체.
6. main 푸시 → GitHub Pages 게시 + 텔레그램 알림(GitHub Action).

> 📈 `progress.html`(진척+퀴즈)·`digest-latest.txt`는 **매일 일일 파이프라인에서도 자동 갱신**(순수 stdlib·$0)된다.
> 루틴은 거기에 더해 **코칭 한마디(`#coach`)**만 통찰로 채운다(라디오 대본과 동일한 보존 패턴).

> 🎧 **오디오(MP3)는 루틴이 만들지 않는다.** 별도 GitHub Actions `radio-audio.yml`(금 17:00 KST,
> 루틴 직후)이 루틴이 갱신한 `#radio-src` 대본을 읽어 Gemini TTS(폴백 gTTS)로 MP3를 만들고
> `docs/radio/`에 커밋 + 텔레그램 발송한다. 루틴은 대본까지만 책임진다.

---

## 붙여넣을 프롬프트 (정본)

너는 영어 학습 복습 시스템의 주간 관리자다. 아래를 **순서대로** 수행해라.
레포는 github.com/ok0327-dot/english-feedback (main, GitHub Pages = main/docs).

### 0단계 — 준비
- 레포를 클론(또는 최신화)하고 `pip install -r requirements.txt`.

### 1단계 — 짤린 일일 피드백 자가복구 (네가 직접 보강)
- `python3 scripts/repair_truncated.py list` 로 짤린(꼬리 섹션이 소실된) 일일 페이지 날짜 목록을 얻어라.
- **각 날짜마다**:
  1. `python3 scripts/repair_truncated.py extract <날짜>` 로 그 페이지의 **온전한 전사**·파일명·수업길이를 읽어라.
  2. `scripts/feedback_spec.md`(피드백 작성 스펙, repo에 포함)를 그대로 따라 **완전한 7섹션 피드백**을 한국어로 새로 작성해라. 전사에 실제로 있는 [Student](=Joey) 발화만 인용하고, Target Grammar 카테고리는 귀납적으로 고른다. 반드시 `Category:` 줄과 `유창성 점수: N/10` 줄을 포함.
  3. 작성한 피드백을 임시 .md 파일로 저장한 뒤 `python3 scripts/repair_truncated.py apply <날짜> <그.md>` 로 페이지를 재생성해라.
- 목록이 비어 있으면(짤린 것 없음) 이 단계는 건너뛴다.
- ⚠️ `apply` 는 metadata.json 을 갱신하므로 **한 번에 하나씩 순차** 실행(동시 실행 금지).

### 2단계 — 주간 스냅샷 + 라디오 + 진척/다이제스트 재생성
- `python3 scripts/build_weekly_review.py` 실행. (1단계 복구로 데이터가 온전해진 상태에서 집계됨.)
- `python3 scripts/build_radio.py` 실행. 가장 최근 주의 누적 피드백으로 `docs/radio.html`(주간 라디오)을 재생성한다.
- `python3 scripts/build_progress.py` 실행. `docs/progress.html`(진척 대시보드 + 복습 퀴즈)을 재생성한다. **기존 `#coach` 코칭 문구는 자동 보존**되니(3단계에서 교체) 안심하고 돌려라.
- `python3 scripts/build_digest.py` 실행. `docs/digest-<주>.txt` + `docs/digest-latest.txt`(NotebookLM 붙여넣기용 다이제스트)를 재생성한다.
- stdout 마지막 줄 `CURRENT_WEEK_FILE=review-2026-Www.html` 로 **현재 주 파일**을 식별.

### 3단계 — 종합문 + 큐레이션을 네 통찰로 교체
- **현재 주 파일**(`docs/<CURRENT_WEEK_FILE>`)의 `<div class="syn" id="synthesis">...</div>` 안 내용을, 그 주 교정·약점·어휘를 실제로 읽고 쓴 **구체적이고 실행가능한 한국어 종합 2~4문장**으로 교체해라. (규칙기반 폴백보다 나아야 의미가 있음. `<b>` 강조 사용 가능, 다른 HTML 구조는 건드리지 말 것.)
- `docs/review-vocab.html`의 `<div class="syn" id="curation">...</div>` 안 내용도, 누적 단어·표현을 읽고 **무엇을 우선 암기/연습할지 짚어주는 한국어 큐레이션 2~3문장**으로 교체해라.
- **현재 주 파일에 `<div class="syn" id="carrot_compare">...</div>` 가 있으면**(그 주 강사 데이터 존재), `docs/carrot/*.json`의 이번 주 날짜 **강사 교정**과 현재 주 페이지의 **AI 교정 표현**을 비교해 **강사·AI가 공통으로 짚은 약점(=진짜 우선순위)과 한쪽만 짚은 사각지대**를 한국어 2~3문장으로 써 교체해라. 끝에 `<span class="muted">— Claude 비교 ($0)</span>`. (carrot_compare div가 없으면 그 주는 강사 데이터가 없는 것이니 건너뛴다.)
- `docs/radio.html`의 `<pre id="radio-src">...</pre>` 안 **라디오 대본**을, **약 15~20분 분량(120~200줄, 200줄 넘기지 않기)**의 **진짜 FM 라디오 같은** 2인 진행 쇼(Joey FM)로 교체해라. **작성 기준 정본 = `scripts/radio_script_spec.md`** — 런다운·한국어(ko) 비율·형식은 전부 거기를 따른다(이 단계와 다르면 스펙이 우선). 규칙기반 베이스라인은 `python3 scripts/build_radio.py --preview <이번 주>` 로 볼 수 있다.
  - **Tutor Rewind(그때 그 수업)가 메인**: 쇼 앞부분에 `docs/carrot/*.json` 의 이번 주 **강사 교정 2~4개**를 하나씩 — **요일 + 그날 수업 주제**(일일 피드백 Topic·강사 메모)로 장면을 열고, 학습자가 실제로 한 말(❌) → 생각할 틈(three, two, one) → 강사 교정(✅) → 쉬운 이유 → 덩어리 반복. AI 일일 피드백도 같은 습관을 짚었으면 "강사와 AI가 둘 다 잡았다 = 진짜 우선순위"라고 말한다. 강사 데이터가 없는 주는 짧게 알리고 AI 교정으로 같은 형식.
  - **한국어로 상기시켜라**: 교정 하나 끝날 때마다 ko **'한 줄 정리'** 1줄, 전반부 뒤 **한국어 중간 정리** 2~3줄, 끝나기 전 **오늘의 한국어 3줄 요약**, 심화 코너마다 핵심 '왜/문화' ko 1줄. ko 는 전체의 약 20~25%(최대 30%), 나머지는 영어 몰입.
  - **게임으로 재미**: Spot the Mistake · Fix it in 3 seconds · Real or Wrong? · Mistake Top 3 Countdown 중 1~2개를 **매주 바꿔** 넣는다. 징글·범퍼("Coming up after the game…")·stay tuned·콜백 같은 라디오 장치는 말로만(효과음 표기 금지).
  - **Why It Happens · Correction Clinic · Culture Corner · Topic Talk** 는 스펙대로: 그 주 1위 습관의 ❌→✅·한국어 사고 vs 영어 사고·문화 대비·rule of thumb, 남은 교정 빠르게, 매주 다른 흥미 이야기 1개, 그 주 주제의 A2~B1 표현 3~5개를 실제 문장 속에서. 학습자 문장은 지어내지 말고 실제 데이터에서만.
  - **난이도 A2~B1** · **문법책 용어 금지(쉬운 말·덩어리로)** — 스펙의 '🗣️ 문법은 쉬운 말로' 참고.
  - 형식 엄수: **한 줄에 `진행자|lang|문장`** (진행자=민지 또는 알렉스만, lang=`en` 또는 `ko`만, 문장 안에 `|` 금지, 빈 줄 금지). **형식이 깨지면 음성 재생·MP3 생성이 안 된다.**
- `docs/progress.html`의 `<div class="syn" id="coach">...</div>` 안 내용을, 그 주 진척(유창성 추세·최다 약점)과 **다음 주 1순위 처방**을 짚는 **한국어 2~3문장 코칭**으로 교체해라. 학습자를 격려하되 구체적으로(예: "이번 주 Subject–Verb Agreement가 또 최다 — 3인칭 단수 -s를 의식하며 한 문장씩"). `<b>` 강조 가능.
- 위 `id` 컨테이너들(`#synthesis`/`#curation`/`#carrot_compare`/`#radio-src`/`#coach`)의 **여는/닫는 태그와 속성은 보존**하고 내부 텍스트만 교체(렌더링·재생 깨짐 방지).

### 4단계 — 커밋 & 푸시
- 변경(복구된 일일 페이지 + 주간 스냅샷 + 종합/큐레이션 + 진척 코칭 + 다이제스트)을 한 커밋으로 main 에 푸시.
- 커밋 메시지 예: `chore(review): 주간 복습 갱신 + 짤린 일일 N건 자가복구`.
- 푸시되면 GitHub Action(`weekly-review-notify.yml`)이 텔레그램으로 자동 알림(시크릿은 루틴이 만지지 않음).

### 원칙
- 데이터 삭제·비가역 작업 금지. 페이지 구조/CSS 변경 금지(텍스트 콘텐츠만).
- 무료 쿼터 보호: Gemini 호출 불필요(이 루틴은 순수 집계 + 너의 글쓰기로 $0).

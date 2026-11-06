"""
진단용 지시문 / prompts for the diagnosis variants (DIAGNOSIS_PLAN 3절).

- 현행(V1·V3): process_lesson 의 지시문을 그대로 쓴다 → 아래 capture() 로 실제 문자열을 얻는다.
- 개선(V2·V4·V5·V6·V7): 현행 보정·화자 검증 지시문에서 '학생 말 고치기'와 '실수 있는 쪽 = 학생' 규칙만 바꾼다.
  현행 지시문의 문구가 바뀌면 바꿀 자리를 못 찾아 **큰 소리로 실패**한다 (조용히 다른 지시문을 쓰지 않게).
- 피드백·검토 지시문은 모든 판이 현행 그대로 (바뀌는 건 보정·화자 단계뿐).
"""
import os

import diagnosis.common  # noqa: F401  (ROOT 경로 준비)

for _k in ("GOOGLE_CREDENTIALS", "GROQ_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.setdefault(_k, "unused")
import process_lesson as pl  # noqa: E402

T, F = "<<<TRANSCRIPT>>>", "<<<FEEDBACK>>>"

IMPROVED_STEP2 = """## STEP 2: 전사 오류 보정 (학생이 한 말은 그대로)

- [Student] 발화의 단어·문법은 **고치지 마세요.** 틀린 문법·어색한 표현도 학생이 실제로 말한 그대로 둡니다 (피드백 단계에서 교정합니다).
- 소리가 비슷해 STT가 **잘못 들은 것이 확실할 때만** 고치고, 고친 단어 바로 뒤에 `[?원래단어]` 를 붙이세요. 예: "I went to Sapporo [?Supporo]"
- 잘못 들은 건지 실제로 틀리게 말한 건지 확신이 없으면 **고치지 말고** 그 줄 끝에 `[?]` 를 붙이세요.
- [Tutor] 발화의 명백한 오인식은 고쳐도 됩니다.
- 소음으로 인한 잡음 텍스트는 제거합니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

IMPROVED_STEP3 = """## STEP 3: 화자 분리

각 발화 앞에 [Tutor] 또는 [Student]를 표시하세요.

⚠️ **문법 실수가 있다/없다는 화자 판단에 쓰지 마세요.** 그렇게 하면 학생이 잘 말한 문장이 튜터 것으로 넘어갑니다.

화자 식별 단서 (우선순위 순):
1순위 — 이름 호명: "Joey"라고 상대를 부르는 쪽 → [Tutor] / 튜터 이름(Bell, Joanna 등)으로 부르는 쪽 → [Student]
2순위 — 대화 역할: 질문·리액션·칭찬·교정·되묻기 → [Tutor] / 대답·한국 생활·업무 등 자기 경험 이야기 → [Student] / "teacher"라고 부르는 쪽 → [Student]
3순위 — 타임스탬프: 세그먼트 사이 1.5초 이상 침묵은 화자 전환 가능성이 높음, 0.5초 미만은 같은 화자의 쉼

📌 일관성 검증: 질문한 사람과 대답한 사람은 다른 화자여야 합니다. 화자를 확신할 수 없는 줄은 끝에 `[?]` 를 붙이세요 (지어내지 않습니다).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

DIARIZED_NOTE = """

📌 **아래 원본은 받아쓰기 모델이 녹음을 직접 듣고 목소리로 나눈 화자 표시(Speaker A/B 등)가 붙어 있습니다.**
화자 구분(누가 어디서 말이 바뀌는지)은 그 표시를 그대로 따르고, 어느 목소리가 [Tutor]·[Student] 인지만 위 단서로 정하세요.
"""


def _capture(fn, *args, **kwargs):
    """process_lesson 함수가 LLM 에 보내는 지시문 문자열을 그대로 가로챈다 (실제 호출 없음)."""
    seen = []

    def fake(prompt, *a, **k):
        seen.append(prompt)
        return "x"
    real = pl.llm_request
    pl.llm_request = fake
    try:
        fn(*args, **kwargs)
    finally:
        pl.llm_request = real
    if len(seen) != 1:
        raise RuntimeError(f"{fn.__name__}: LLM 호출이 {len(seen)}번 — 지시문 구조가 바뀜")
    return seen[0]


def _between(text, start, end):
    a = text.index(start)
    b = text.index(end, a)
    return a, b


def current_clean(raw, segments):
    return _capture(pl.clean_transcript, raw, segments)


def improved_clean(raw, segments, diarized=False):
    """현행 보정 지시문에서 STEP 1 의 '영어 실력 차이' 단서, STEP 2·3 을 개선판으로 바꾼다."""
    p = current_clean(raw, segments)
    hint = "- **영어 실력 차이**: 어떤 발화들이 문법적으로 완벽하고, 어떤 발화들에 실수가 있는가?\n"
    if hint not in p:
        raise RuntimeError("현행 보정 지시문 STEP 1 문구가 바뀜 — prompts.py 갱신 필요")
    p = p.replace(hint, "")
    a, b = _between(p, "## STEP 2:", "## STEP 3:")
    p = p[:a] + IMPROVED_STEP2 + p[b:]
    a, b = _between(p, "## STEP 3:", "## 출력 포맷")
    p = p[:a] + IMPROVED_STEP3 + p[b:]
    if diarized:
        p = p.replace("\n원본 전사:\n", DIARIZED_NOTE + "\n원본 전사:\n", 1)
    for banned in ("영문법 실수가 있는 쪽이 [Student]", "문맥상 맞지 않는 단어를 올바른 단어로 수정"):
        if banned in p:
            raise RuntimeError(f"개선 지시문에 현행 규칙이 남음: {banned}")
    return p


def current_verify(transcript):
    return _capture(pl.verify_speaker_labels, transcript)


def improved_verify(transcript):
    """현행 화자 검증의 1번 기준('영어 실력 일관성' = 실수 있는 쪽이 학생)을 빼고 호명·흐름 기준으로."""
    p = current_verify(transcript)
    a = p.index("1. **영어 실력 일관성**")
    b = p.index("\n", a)
    return p[:a] + ("1. **실수 여부로 판단 금지**: 문법이 완벽한지/틀렸는지는 화자 단서로 쓰지 말 것 "
                    "(학생이 잘 말한 문장도 [Student]). 확신 없는 줄은 끝에 [?]") + p[b:]


def feedback_template():
    """피드백 지시문 — 모든 판이 같다. 직전 카테고리 회피 목록은 비워 조건을 고정한다."""
    return _capture(pl.generate_feedback, T, recent_categories=[])


def review_template():
    return _capture(pl.review_feedback, T, F)


def segments_text(segments):
    return pl._format_segments_with_gaps(segments) if segments else ""

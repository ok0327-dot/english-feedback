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

# 개선판 조각은 2026-11-10 부터 process_lesson 의 기본값이다 (승격). 여기서는 같은 것을 다시 가리킨다.
IMPROVED_STEP2, IMPROVED_STEP3 = pl.IMPROVED_STEP2, pl.IMPROVED_STEP3

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


def current_clean(raw, segments):
    """현행판(V1·V3) = 승격 전 지시문."""
    return _capture(pl.clean_transcript, raw, segments, improved=False)


def improved_clean(raw, segments, diarized=False):
    """개선판 — 학생 말 고치지 않기 · '실수 있는 쪽 = 학생' 규칙 없음 (지금 매일 흐름의 기본값)."""
    p = _capture(pl.clean_transcript, raw, segments, improved=True)
    if diarized:
        p = p.replace("\n원본 전사:\n", DIARIZED_NOTE + "\n원본 전사:\n", 1)
    for banned in ("영문법 실수가 있는 쪽이 [Student]", "문맥상 맞지 않는 단어를 올바른 단어로 수정"):
        if banned in p:
            raise RuntimeError(f"개선 지시문에 현행 규칙이 남음: {banned}")
    return p


def current_verify(transcript):
    return _capture(pl.verify_speaker_labels, transcript, improved=False)


def improved_verify(transcript):
    """화자 검증 개선판 — 실수 여부를 화자 단서로 쓰지 않는다."""
    return _capture(pl.verify_speaker_labels, transcript, improved=True)


def feedback_template():
    """피드백 지시문 — 모든 판이 같다. 직전 카테고리 회피 목록은 비워 조건을 고정한다."""
    return _capture(pl.generate_feedback, T, recent_categories=[])


def review_template():
    return _capture(pl.review_feedback, T, F)


def segments_text(segments):
    return pl._format_segments_with_gaps(segments) if segments else ""

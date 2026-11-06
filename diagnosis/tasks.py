"""
Claude·Codex 판 작업지 / task sheets for the Claude (V5, V7, V7′) and Codex (V6) variants.

Gemini 판처럼 API 로 부르지 않고, 각 엔진이 작업지 하나를 읽어 4단계를 **같은 지시문으로 차례대로** 수행한다.
  1 보정·화자 (개선 지시문, 판에 따라 입력이 다름)  2 화자 검증 (개선)  3 피드백 (현행)  4 검토 (현행)
결과는 .diag/out/<판>/<날짜>.json — {"transcript": 2단계 결과, "feedback": 4단계 결과, "engine": 모델 이름, ...}
입력:
  V5·V6 : Whisper 원본 + 구간 시각
  V7    : gemini-3.5-transcribe 가 목소리로 화자를 나눈 받아쓰기 (diarized)
  V7′   : 같은 받아쓰기에서 화자 표시·시각을 지운 글 (단어 효과만 보기)
실행: python3 -m diagnosis.tasks build
"""
import os
import re
import sys

from diagnosis import prompts as P
from diagnosis.common import (ARCHIVE_NAME, DIAG, INPUT, SAMPLES, load_archive, out_path, read_json, require_frozen_items,
                              sha)

TASKS = os.path.join(DIAG, "tasks")
ENGINE = {"V5": "Claude", "V6": "Codex(GPT)", "V7": "Claude", "V7p": "Claude"}

SHEET = """# 진단 작업지 — {variant} · {date} · 엔진 {engine}

아래 4단계를 **순서대로** 수행하라. 각 단계의 지시문은 바꾸지 말고 그대로 따른다.
앞 단계의 결과가 다음 단계의 입력이다 (`{T}` 자리에 2단계 결과, `{F}` 자리에 3단계 결과를 넣는다).
다른 파일이나 웹을 보지 말 것. 끝나면 결과를 아래 JSON 하나로 `{out}` 에 저장한다:
{{"variant": "{variant}", "date": "{date}", "engine": "<실제 모델 이름>", "source_text_sha": "{src_sha}",
 "cleaned": "<1단계 결과>", "transcript": "<2단계 결과>", "feedback_draft": "<3단계 결과>", "feedback": "<4단계 결과>"}}

## 1단계 — 보정·화자 (지시문 지문 {s1})
{p1}

## 2단계 — 화자 검증 (지시문 지문 {s2})
{p2}

## 3단계 — 피드백 (지시문 지문 {s3})
{p3}

## 4단계 — 검토 (지시문 지문 {s4})
{p4}
"""


def strip_diarization(text):
    """'[01:23] Speaker A: …' → '…' (V7′: 단어만 남기고 화자·시각 표시를 지움)."""
    t = re.sub(r"\[\d{1,2}:\d{2}(?::\d{2})?\]", " ", text or "")
    t = re.sub(r"(?im)^\s*speaker\s+[a-z0-9]+\s*:\s*", "", t)
    return re.sub(r"[ \t]+", " ", t).strip()


def source_for(variant, date, rec):
    """판이 1단계에서 읽을 (글, 구간, 받아쓰기 화자 표시 여부)."""
    if variant in ("V5", "V6"):
        return rec["text"], rec.get("segments") or [], False
    ears = read_json(out_path("V7ears", date))
    if not ears or not ears.get("text"):
        raise SystemExit(f"❌ V7 받아쓰기 없음({date}) — run_transcribe 먼저")
    return (ears["text"], [], True) if variant == "V7" else (strip_diarization(ears["text"]), [], False)


def build(variants=("V5", "V6", "V7", "V7p")):
    require_frozen_items()
    arch = load_archive(os.path.join(INPUT, ARCHIVE_NAME))
    fb, rv = P.feedback_template(), P.review_template()
    p2 = P.improved_verify(P.T)
    made = 0
    for v in variants:
        for date, fname in sorted(SAMPLES.items()):
            try:
                text, segs, diar = source_for(v, date, arch[fname])
            except SystemExit as e:
                print(f"⏭️ {v} {date}: {e}")
                continue
            p1 = P.improved_clean(text, segs, diarized=diar)
            sheet = SHEET.format(variant=v, date=date, engine=ENGINE[v], T=P.T, F=P.F, out=out_path(v, date),
                                 src_sha=sha(text), s1=sha(p1), s2=sha(p2), s3=sha(fb), s4=sha(rv),
                                 p1=p1, p2=p2, p3=fb, p4=rv)
            os.makedirs(os.path.join(TASKS, v), exist_ok=True)
            with open(os.path.join(TASKS, v, f"{date}.md"), "w", encoding="utf-8") as f:
                f.write(sheet)
            made += 1
    print(f"📝 작업지 {made}개 → {TASKS}")


if __name__ == "__main__":
    build() if (sys.argv[1:] or [""])[0] == "build" else print(__doc__)

"""
V1~V4 실행기 (Gemini 판) / runner for the Gemini variants (DIAGNOSIS_PLAN 3절).

- 모델 고정: 본 흐름의 모델 사다리·Groq 대체를 끄고 판마다 모델 하나만 쓴다. 실패하면 그 건은 '실패'로 남는다
  (현행 clean_transcript 처럼 조용히 원본을 돌려주는 일이 없게, 실패를 가로채 기록한다).
- 순서: 판×수업 20건을 고정 시드로 섞어 돌린다 — 판별로 몰아 돌리면 특정 판만 한도·장애 날을 겪는다.
- 이어서 돌리기: 결과 파일이 있으면 건너뛴다. 하루 한도에 걸리면 멈추고, 다음 날 다시 실행하면 이어 간다.
- 기록: 단계별 지시문 지문(sha)·모델·토큰을 결과와 실행 기록부(manifest)에 남긴다.

실행: python3 -m diagnosis.run_gemini preflight   # V3·V4 에 쓸 최신 무료 Flash 를 한 번 정해 고정
      python3 -m diagnosis.run_gemini run [--max N]
"""
import json
import os
import random
import sys
import time

from diagnosis import prompts as P
from diagnosis.common import (DIAG, INPUT, SAMPLES, ARCHIVE_NAME, atomic_write_json, load_archive, manifest_add,
                              out_path, read_json, require_frozen_items, sha)

pl = P.pl
MODELS_PATH = os.path.join(DIAG, "models.json")
BASE_MODEL = "gemini-2.5-flash"
LATEST_CANDIDATES = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash"]
VARIANTS = {  # 판: (보정·화자 지시문, 모델 키)
    "V1": ("current", "base"),
    "V2": ("improved", "base"),
    "V3": ("current", "latest"),
    "V4": ("improved", "latest"),
}
SEED = 20261106


class Stop(Exception):
    """하루 한도 등으로 오늘은 더 못 돌림."""


def schedule(dates=None, seed=SEED):
    jobs = [(v, d) for v in VARIANTS for d in sorted(dates or SAMPLES)]
    random.Random(seed).shuffle(jobs)
    return jobs


def model_for(key):
    if key == "base":
        return BASE_MODEL
    m = (read_json(MODELS_PATH) or {}).get("latest")
    if not m:
        raise SystemExit("❌ V3·V4 모델 미고정 — python3 -m diagnosis.run_gemini preflight 먼저")
    return m


def preflight():
    """최신 무료 Flash 를 3.8 → 3.7 → 3.5 순으로 한 번 시험해 처음 응답한 모델로 고정 (DIAGNOSIS_PLAN ※)."""
    if read_json(MODELS_PATH):
        print(f"ℹ️ 이미 고정됨: {read_json(MODELS_PATH)}")
        return
    for m in LATEST_CANDIDATES:
        try:
            t0 = time.time()
            pl.gemini_request("Reply with exactly: OK", max_tokens=1024, thinking_budget=1024, model=m, timeout=90)
            atomic_write_json(MODELS_PATH, {"latest": m, "tried": LATEST_CANDIDATES, "seconds": round(time.time() - t0)})
            print(f"🔒 V3·V4 모델 고정: {m}")
            return
        except Exception as e:  # noqa: BLE001
            print(f"   {m}: 실패 ({str(e)[:120]})")
    raise SystemExit("❌ 최신 무료 Flash 가 모두 응답 없음 — V3·V4 는 빼고 기록 (DIAGNOSIS_PLAN)")


class Pinned:
    """LLM 호출을 모델 하나로 고정하고, 실패·토큰을 기록한다."""

    def __init__(self, model):
        self.model, self.calls = model, []
        self._post = pl.requests.post

    def __enter__(self):
        def post(url, *a, **k):
            r = self._post(url, *a, **k)
            if "generativelanguage" in url and r.status_code == 200:
                u = (r.json() or {}).get("usageMetadata") or {}
                self.calls[-1]["tokens"] = {"in": u.get("promptTokenCount"), "out": u.get("candidatesTokenCount"),
                                            "think": u.get("thoughtsTokenCount")}
            return r

        def llm(prompt, max_tokens=4096, temperature=0.3, timeout=120, system_msg=None, thinking_budget=2048):
            self.calls.append({"prompt_sha": sha(prompt), "model": self.model})
            try:
                return pl.gemini_request(prompt, max_tokens, temperature, timeout, system_msg, thinking_budget,
                                         model=self.model)
            except Exception as e:
                self.calls[-1]["error"] = str(e)[:300]
                raise
        pl.requests.post, self._llm, pl.llm_request = post, pl.llm_request, llm
        return self

    def __exit__(self, *exc):
        pl.requests.post, pl.llm_request = self._post, self._llm

    def ask(self, prompt, max_tokens, temperature, thinking_budget=2048):
        return pl.llm_request(prompt, max_tokens, temperature, 120, None, thinking_budget)

    def failed(self):
        return any("error" in c for c in self.calls)


def run_one(variant, date, rec):
    style, mkey = VARIANTS[variant]
    model = model_for(mkey)
    raw, segs = rec["text"], rec.get("segments") or []
    steps = {}
    with Pinned(model) as llm:
        if style == "current":
            cleaned = pl.clean_transcript(raw, segs)            # 현행 함수 그대로 (실패 시 원본을 돌려줌 → 아래서 잡음)
            if llm.failed():
                raise RuntimeError(f"보정 실패: {llm.calls[-1].get('error')}")
            verified = pl.verify_speaker_labels(cleaned)
            if llm.failed():
                raise RuntimeError(f"화자 검증 실패: {llm.calls[-1].get('error')}")
        else:
            cleaned = llm.ask(P.improved_clean(raw, segs), 24576, 0.3)   # 현행과 같은 길이·온도
            verified = llm.ask(P.improved_verify(cleaned), 24576, 0.2)
        feedback = pl.generate_feedback(verified, recent_categories=[])
        if llm.failed():
            raise RuntimeError(f"피드백 실패: {llm.calls[-1].get('error')}")
        reviewed = pl.review_feedback(verified, feedback)
        if llm.failed():
            raise RuntimeError(f"검토 실패: {llm.calls[-1].get('error')}")
        steps = {"cleaned": cleaned, "verified": verified, "feedback_draft": feedback}
        calls = llm.calls
    return {"variant": variant, "date": date, "model": model, "style": style, "source_file": rec["source_file"],
            "transcript": verified, "feedback": reviewed, "steps": steps, "calls": calls}


def is_quota(err):
    s = str(err)
    return "하루 무료 한도" in s or "429" in s or "exceeded your current quota" in s


def run(max_jobs=None):
    require_frozen_items()
    arch = load_archive(os.path.join(INPUT, ARCHIVE_NAME))
    done = 0
    for variant, date in schedule():
        if os.path.exists(out_path(variant, date)):
            continue
        if max_jobs is not None and done >= max_jobs:
            break
        rec = arch.get(SAMPLES[date])
        if not rec:
            raise SystemExit(f"❌ 원본 없음: {SAMPLES[date]} — prep 먼저")
        t0 = time.time()
        try:
            out = run_one(variant, date, rec)
        except Exception as e:  # noqa: BLE001
            manifest_add({"variant": variant, "date": date, "status": "failed", "error": str(e)[:300]})
            if is_quota(e):
                print(f"⏸️ {variant} {date}: 한도 — 오늘은 여기까지. 내일 다시 실행하면 이어서 돈다")
                return
            print(f"⚠️ {variant} {date}: 실패 ({str(e)[:160]}) — 다음 건으로")
            continue
        out["seconds"] = round(time.time() - t0)
        atomic_write_json(out_path(variant, date), out)
        tok = sum((c.get("tokens") or {}).get("in") or 0 for c in out["calls"])
        manifest_add({"variant": variant, "date": date, "status": "done", "model": out["model"],
                      "prompt_shas": [c["prompt_sha"] for c in out["calls"]], "input_tokens": tok})
        done += 1
        print(f"✅ {variant} {date} ({out['model']}, {out['seconds']}초, 입력 토큰 {tok})")
    left = [j for j in schedule() if not os.path.exists(out_path(*j))]
    print(f"남은 건: {len(left)}")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "preflight":
        preflight()
    elif cmd == "run":
        n = int(argv[argv.index("--max") + 1]) if "--max" in argv else None
        run(n)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)

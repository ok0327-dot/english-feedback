#!/usr/bin/env python3
"""
🌗 그림자 실행 (품질 개선 계획 2단계) / shadow run — Claude 가 Whisper 원본을 직접 읽고 고품질판 피드백을 만든다.

- 매일 실행(📚 English Lesson Feedback)이 끝나면 이어서 돈다. 본 흐름·메일·main·복습 페이지는 **건드리지 않는다.**
- 최근 며칠의 main 복습 페이지 중 고품질판이 아직 없는 수업을 찾아, Drive 보관 파일의 **Whisper 원본**으로
  4단계(보정·화자 → 화자 검증 → 피드백 → 검토)를 Claude 로 수행한다.
  · 보정·화자 지시문은 개선판(학생 말 고치지 말 것 · '실수 있는 쪽 = 학생' 규칙 삭제) — diagnosis/prompts.py
  · 피드백·검토 지시문은 main 과 같다 (비교를 공정하게)
- 결과는 shadow 브랜치에만: docs-shadow/<날짜>.html (공개 수준 = main 페이지와 같음) · shadow/<날짜>.json · shadow/runs.jsonl.
  Whisper 원본은 어디에도 저장하지 않는다. 로그에 전사·피드백 내용을 찍지 않는다 (공개 저장소).
- Claude 는 구독 토큰(CLAUDE_CODE_OAUTH_TOKEN)으로 `claude -p --tools ""` — 도구 없이 글만 주고받는다.
- 이미 있는 수업은 건너뛴다(중복 0). 실패한 수업은 기록만 남기고 다음 실행이 다시 시도한다.

실행: python3 scripts/shadow_feedback.py --shadow-dir DIR [--days 3] [--max 2]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
for _k in ("GROQ_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):  # 이 단계에선 안 쓰지만 import 때 필수 → 더미
    os.environ.setdefault(_k, "unused")
import process_lesson as pl  # noqa: E402
from diagnosis import prompts as P  # noqa: E402
from diagnosis.common import atomic_write_json, sha  # noqa: E402

MODEL = os.environ.get("SHADOW_MODEL", "").strip() or "opus"
SYSTEM = ("You are an expert English-speaking tutor's assistant for a Korean adult learner. "
          "Follow the user's instructions exactly and output only what they ask for — no preamble.")
CLAUDE_TIMEOUT = 900


def claude(prompt, runner=None):
    """Claude 한 번 호출 → (본문, 사용량 dict). 도구는 모두 끈다(글만 주고받기)."""
    if runner:
        return runner(prompt)
    t0 = time.time()
    r = subprocess.run(["claude", "-p", "--tools", "", "--output-format", "json", "--model", MODEL,
                        "--system-prompt", SYSTEM], input=prompt, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT)
    try:
        d = json.loads(r.stdout)
    except ValueError:
        raise RuntimeError(f"claude 출력 해석 실패 (exit {r.returncode}): {r.stderr[-300:]}")
    if d.get("is_error") or not (d.get("result") or "").strip():
        raise RuntimeError(f"claude 오류: {d.get('subtype')} {d.get('api_error_status') or ''} {str(d.get('result'))[:200]}")
    u = d.get("usage") or {}
    return d["result"], {"model": ",".join((d.get("modelUsage") or {}).keys()) or MODEL,
                         "in": u.get("input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0),
                         "cache_read": u.get("cache_read_input_tokens", 0), "out": u.get("output_tokens", 0),
                         "cost_usd_equiv": d.get("total_cost_usd"), "seconds": round(time.time() - t0)}


def pending(shadow_dir, days, today=None):
    """최근 days 일의 main 복습 페이지 중 고품질판이 없는 것 → [(slug, 페이지의 첫 녹음 파일명)] (오래된 것부터)."""
    today = today or datetime.now(pl.KST)
    cutoff = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    out = []
    for name in sorted(os.listdir("docs")):
        if not (name.startswith("20") and name.endswith(".html")):
            continue
        slug = name[:-5]
        if slug[:10] < cutoff or os.path.exists(os.path.join(shadow_dir, "shadow", f"{slug}.json")):
            continue
        rec = pl._page_recording(os.path.join("docs", name))
        if rec:
            out.append((slug, rec))
    return out


def archive_records(content):
    recs = []
    for line in content.decode("utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("source_file") and r.get("text") is not None:
            recs.append(r)
    return recs


def lesson_parts(page_recording, records):
    """페이지의 첫 녹음이 들어 있는 수업(이어짐 기준 묶음)의 원본 기록들. 같은 녹음이 여러 줄이면 처음 것."""
    seen, recs = set(), []
    for r in records:
        start = pl.recording_start(r["source_file"])
        if start and r["source_file"] not in seen:
            seen.add(r["source_file"])
            recs.append({"name": r["source_file"], "start": start,
                         "size": float(r.get("duration") or 0) * pl.AUDIO_BYTES_PER_SEC, "rec": r})
    for group in pl.group_into_lessons(recs):
        if page_recording in [p["name"] for p in group]:
            return [p["rec"] for p in group]
    return []


def recent_categories(slug):
    meta = pl.load_metadata("docs")
    return [meta[k].get("target_grammar") for k in sorted((k for k in meta if k < slug), reverse=True)[:5]
            if meta.get(k, {}).get("target_grammar")]


def make_one(slug, parts, shadow_dir, runner=None):
    raw, duration, segments = pl.join_transcripts([(r["text"], r.get("duration") or 0, r.get("segments")) for r in parts])
    if not raw.strip():
        raise RuntimeError("원본 전사가 비어 있음")
    steps, usage = [], []

    def step(name, prompt):
        text, u = claude(prompt, runner)
        steps.append({"step": name, "prompt_sha": sha(prompt)})
        usage.append(dict(u, step=name))
        return text

    cleaned = step("clean", P.improved_clean(raw, segments))
    verified = step("verify", P.improved_verify(cleaned))
    fb_prompt = pl_capture_feedback(verified, recent_categories(slug))
    feedback = step("feedback", fb_prompt)
    reviewed = step("review", P.review_template().replace(P.T, verified).replace(P.F, feedback))

    names = [r["source_file"] for r in parts]
    shown = names[0] + (f" 외 {len(names) - 1}개" if len(names) > 1 else "")
    date_str = datetime.strptime(slug[:10], "%Y-%m-%d").strftime("%Y년 %m월 %d일")
    page = pl.generate_review_page(verified, reviewed, shown, duration, date_str)
    page = page.replace("<body>", "<body><div style=\"background:#312e81;color:#fff;padding:8px 16px;font:14px sans-serif\">"
                        "🌗 그림자판 — Claude 가 Whisper 원본으로 만든 비교용 피드백 (메일로 가지 않음)</div>", 1)
    os.makedirs(os.path.join(shadow_dir, "docs-shadow"), exist_ok=True)
    with open(os.path.join(shadow_dir, "docs-shadow", f"{slug}.html"), "w", encoding="utf-8") as f:
        f.write(page)
    atomic_write_json(os.path.join(shadow_dir, "shadow", f"{slug}.json"), {
        "slug": slug, "recordings": names, "duration": duration, "engine": "claude", "requested_model": MODEL,
        "steps": steps, "usage": usage, "transcript": verified, "feedback": reviewed,
        "created_at": datetime.now(pl.KST).isoformat(timespec="seconds")})
    return usage


def pl_capture_feedback(transcript, cats):
    """main 의 피드백 지시문을 그대로 (직전 카테고리 회피 목록까지 main 과 같은 규칙)."""
    return P._capture(pl.generate_feedback, transcript, recent_categories=cats)


def log_run(shadow_dir, entry):
    os.makedirs(os.path.join(shadow_dir, "shadow"), exist_ok=True)
    entry = dict(entry, at=datetime.now(pl.KST).isoformat(timespec="seconds"))
    with open(os.path.join(shadow_dir, "shadow", "runs.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run(shadow_dir, days=3, max_lessons=2, service=None, runner=None):
    todo = pending(shadow_dir, days)
    if not todo:
        print(f"ℹ️ 최근 {days}일에 새로 만들 그림자판 없음")
        return {"done": 0, "failed": 0}
    status, _, content = pl.read_raw_archive(service or pl.get_drive_service())
    if status != "ok":
        print(f"⚠️ 보관 파일 상태 '{status}' — 그림자 실행 건너뜀")
        return {"done": 0, "failed": 0}
    records = archive_records(content)
    done = failed = 0
    for slug, rec in todo[:max_lessons]:
        parts = lesson_parts(rec, records)
        t0 = time.time()
        if not parts:
            log_run(shadow_dir, {"slug": slug, "status": "no_raw"})
            print(f"⏭️ {slug}: 원본 없음 (보관 전) — 다음 실행에서")
            continue
        try:
            usage = make_one(slug, parts, shadow_dir, runner)
        except Exception as e:  # noqa: BLE001 — 한 수업 실패가 나머지를 막지 않게
            failed += 1
            log_run(shadow_dir, {"slug": slug, "status": "failed", "error": str(e)[:300],
                                 "seconds": round(time.time() - t0)})
            print(f"⚠️ {slug}: 실패 ({str(e)[:160]}) — 다음 실행이 다시 시도")
            continue
        done += 1
        tot = {k: sum(u.get(k) or 0 for u in usage) for k in ("in", "cache_write", "cache_read", "out")}
        log_run(shadow_dir, dict({"slug": slug, "status": "done", "seconds": round(time.time() - t0)}, **tot))
        print(f"🌗 {slug}: 그림자판 완료 ({round(time.time() - t0)}초 · 출력 토큰 {tot['out']} · 입력 {tot['in'] + tot['cache_write'] + tot['cache_read']})")
    return {"done": done, "failed": failed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shadow-dir", required=True)
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--max", type=int, default=2)
    a = ap.parse_args()
    r = run(os.path.abspath(a.shadow_dir), a.days, a.max)
    sys.exit(1 if r["failed"] and not r["done"] else 0)


if __name__ == "__main__":
    main()

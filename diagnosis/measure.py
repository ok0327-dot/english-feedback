"""
측정·요약 / measures and summary (DIAGNOSIS_PLAN 4절·5절).

M1 학생 발화 변경(설명용) · M3 강사 교정 포착 · M4 지어낸 인용 · M6 비용 · M7 실제 실수 보존.
결과 파일: .diag/out/<판>/<날짜>.json — {"transcript": 최종 전사, "feedback": 피드백 마크다운, "calls": [...]}
           (V7·V7′ 처럼 받아쓰기가 다른 판은 "source_text": 그 판이 읽은 전사)
경계 사례(M3 겹침 0.35~0.5)와 보정용 표본은 판 이름을 가리고 섞어 .diag/blind_*.json 으로 뽑는다 →
Claude 가 만든 판(V5·V7)을 Claude 가 채점하지 않도록 코덱스가 판정한다.

실행: python3 -m diagnosis.measure
"""
import difflib
import glob
import json
import os
import random
import re

from diagnosis.common import (ARCHIVE_NAME, DIAG, INPUT, OUT, SAMPLES, atomic_write_json, best_window, has_ngram,
                              load_archive, read_json, require_frozen_items, words)

FUNCTION = set("a an the to in on at for of with from is are was were be been am do does did have has had will "
               "would can could i'm it's that this those these".split())


def correction_pairs(md):
    """피드백 마크다운 → [(학생 원문, 교정)]. '❌ …: 원문' 다음 '✅ …: 교정' 줄과 ❌/✅ 열이 있는 표를 읽는다."""
    pairs, lines = [], (md or "").splitlines()
    cols = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if any("❌" in c for c in cells) and any("✅" in c for c in cells):
                cols = (next(k for k, c in enumerate(cells) if "❌" in c), next(k for k, c in enumerate(cells) if "✅" in c))
                continue
            if cols and not set(s) <= set("|-: "):
                if max(cols) < len(cells):
                    pairs.append((_clean(cells[cols[0]]), _clean(cells[cols[1]])))
                continue
        else:
            cols = None
        if "❌" in s and ":" in s:
            nxt = next((lines[j].strip() for j in range(i + 1, min(i + 4, len(lines))) if "✅" in lines[j]), "")
            if nxt:
                pairs.append((_clean(s.split(":", 1)[1]), _clean(nxt.split(":", 1)[-1])))
    return [(w, r) for w, r in pairs if w]


def _clean(t):
    return re.sub(r"\*\*|`|^[\"“]|[\"”]$|\[(?:Student|Tutor)\]", "", t or "").strip()


def m3_captured(item, pairs):
    """강사 항목을 잡았나: ❌ 인용이 강사 원문과 겹침 ≥ 0.5 이고 ✅ 에 고친 묶음이 하나라도 있으면."""
    best = 0.0
    for wrong, right in pairs:
        score = best_window(item["original"], words(wrong))[0]
        best = max(best, score)
        if score >= 0.5 and any(has_ngram(words(right), k) for k in item["fix_keys"]):
            return "yes", score
    return ("borderline" if 0.35 <= best < 0.5 else "no"), best  # 문장은 찾았는데 고친 말이 없으면 '못 잡음'


def m4_fabricated(pairs, own_text, whisper_text):
    """학생 인용 중 그 판이 읽은 전사와 Whisper 원본 **둘 다에** 비슷한 구간(겹침 ≥ 0.85)이 없는 것."""
    own, wh = words(own_text), words(whisper_text)
    return [w for w, _ in pairs if best_window(w, own)[0] < 0.85 and best_window(w, wh)[0] < 0.85]


def m7_preserved(item, text):
    """강사가 적은 실수가 전사에 틀린 그대로 남았나: 'yes' / 'fixed'(고쳐짐) / 'missing'(그 문장을 못 찾음)."""
    ws = words(text)
    score, a, b = best_window(item["original"], ws)
    if score < 0.5:
        return "missing"
    win = ws[max(0, a - 3):b + 3]
    return "yes" if all(has_ngram(win, k) for k in item["error_keys"]) else "fixed"


def m1_changes(raw, final):
    """원본 → 최종 전사에서 바뀐 단어 수 (기능어 = 문법형, 나머지 = 소리형·기타). 판정에는 안 씀."""
    a, b = words(raw), words(final)
    gram = other = 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op in ("replace", "delete", "insert"):
            for w in set(a[i1:i2]) ^ set(b[j1:j2]):
                if w in FUNCTION:
                    gram += 1
                else:
                    other += 1
    return {"grammar_like": gram, "other": other}


def source_text(variant, date, result, whisper):
    """그 판이 1단계에서 실제로 읽은 글 — V7 은 받아쓰기 원문, V7′ 은 화자 표시를 지운 받아쓰기, 나머지는 Whisper.
    결과 파일에 적힌 값에 기대지 않고 원래 입력에서 다시 만든다 (코덱스 리뷰: V7 판 M4 가 Whisper 로 대신 비교되던 문제)."""
    if variant in ("V7", "V7p"):
        ears = (read_json(os.path.join(OUT, "V7ears", f"{date}.json")) or {}).get("text")
        if not ears:
            raise SystemExit(f"❌ {variant} {date}: V7 받아쓰기 원문이 없어 M4 를 잴 수 없음")
        if variant == "V7p":
            from diagnosis.tasks import strip_diarization
            return strip_diarization(ears)
        return ears
    return result.get("source_text") or whisper


def tokens(calls):
    t = {"in": 0, "out": 0}
    for c in calls or []:
        for k in t:
            t[k] += ((c.get("tokens") or {}).get(k) or 0)
    return t


def main():
    items = [i for i in require_frozen_items()["items"] if i["kind"] == "grammar"]
    arch = load_archive(os.path.join(INPUT, ARCHIVE_NAME))
    raw = {d: arch[f]["text"] for d, f in SAMPLES.items() if f in arch}
    summary, blind = {}, []
    for vdir in sorted(glob.glob(os.path.join(OUT, "*"))):
        v = os.path.basename(vdir)
        if not os.path.isdir(vdir) or v == "V7ears":
            continue
        s = {"lessons": 0, "m3_yes": 0, "m3_border": 0, "m4_fabricated": 0, "m7_yes": 0, "m7_fixed": 0, "m7_missing": 0,
             "m1": {"grammar_like": 0, "other": 0}, "tokens": {"in": 0, "out": 0}}
        for path in sorted(glob.glob(os.path.join(vdir, "*.json"))):
            r = read_json(path)
            d = r["date"]
            pairs = correction_pairs(r["feedback"])
            s["lessons"] += 1
            for it in (i for i in items if i["date"] == d):
                res, score = m3_captured(it, pairs)
                s["m3_yes"] += res == "yes"
                if res == "borderline":
                    s["m3_border"] += 1
                    blind.append({"item": it["id"], "original": it["original"], "better": it["better"],
                                  "feedback_pairs": pairs, "_variant": v})
                s["m7_" + m7_preserved(it, r["transcript"])] += 1
            s["m4_fabricated"] += len(m4_fabricated(pairs, source_text(v, d, r, raw.get(d, "")), raw.get(d, "")))
            for k, n in m1_changes(raw.get(d, ""), r["transcript"]).items():
                s["m1"][k] += n
            for k, n in tokens(r.get("calls")).items():
                s["tokens"][k] += n
        summary[v] = s
    # Whisper 원본 자체의 M7 (기준선)
    base = {"m7_yes": 0, "m7_fixed": 0, "m7_missing": 0}
    for it in items:
        if it["date"] in raw:
            base["m7_" + m7_preserved(it, raw[it["date"]])] += 1
    summary["Whisper원본"] = base
    random.Random(7).shuffle(blind)
    for k, b in enumerate(blind):
        b["blind_id"] = f"B{k + 1:02d}"
    atomic_write_json(os.path.join(DIAG, "blind_key.json"), {b["blind_id"]: b.pop("_variant") for b in blind})
    atomic_write_json(os.path.join(DIAG, "blind_borderline.json"), blind)
    atomic_write_json(os.path.join(DIAG, "summary.json"), summary)
    print(f"{'판':<12} 수업  M3포착  경계  M4지어냄  M7보존/고쳐짐/못찾음  M1문법형  입력토큰")
    for v, s in summary.items():
        if "lessons" in s:
            print(f"{v:<12} {s['lessons']:>3}  {s['m3_yes']:>3}/{len([i for i in items])}  {s['m3_border']:>4}  {s['m4_fabricated']:>6}"
                  f"   {s['m7_yes']}/{s['m7_fixed']}/{s['m7_missing']}  {s['m1']['grammar_like']:>8}  {s['tokens']['in']:>8}")
        else:
            print(f"{v:<12}   -       -     -       -   {s['m7_yes']}/{s['m7_fixed']}/{s['m7_missing']}")
    print(f"경계 사례 {len(blind)}건 → .diag/blind_borderline.json (판 이름 가림, 코덱스 판정용)")


if __name__ == "__main__":
    main()

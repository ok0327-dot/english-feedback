#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📓 NotebookLM 다이제스트 빌더 / NotebookLM digest builder.

  사용자는 Google AI Pro(NotebookLM) 구독을 보유. NotebookLM의 Audio Overview는
  2인 MC 영어 팟캐스트를 매우 자연스럽게 무료로 생성한다(현재 TTS보다 품질↑).
  이 스크립트는 '그 주 학습 다이제스트'를 NotebookLM에 붙여넣기 좋은 깔끔한 텍스트로 만든다.

  - 단일 진실원천 = docs/data/*.json + docs/carrot/*.json. 외부 의존성 0.
  - 산출물:
      docs/digest-<YYYY-Www>.txt  (그 주 아카이브)
      docs/digest-latest.txt      (라디오 페이지 '복사' 버튼이 가져가는 고정 파일)

The user has a Google AI Pro (NotebookLM) subscription. NotebookLM's Audio Overview makes
a very natural 2-host English podcast for free. This builds a clean weekly study digest to
paste into NotebookLM. Pure stdlib. Writes a dated archive + a stable digest-latest.txt.
"""
import glob, os, json, datetime
from collections import Counter, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOCS = os.path.join(ROOT, "docs")
DATA = os.path.join(DOCS, "data")
CARROT = os.path.join(DOCS, "carrot")
CUTOFF = "2026-05-08"

def load_rows():
    out = []
    for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        if os.path.basename(f)[:10] < CUTOFF:
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        iso = d.get("iso")
        d["iso"] = tuple(iso) if isinstance(iso, list) else iso
        d.setdefault("pairs", []); d.setdefault("vocab", [])
        out.append(d)
    out.sort(key=lambda r: r.get("date", ""))
    return out

def week_label(iso): return f"{iso[0]}-W{iso[1]:02d}"
def week_range(iso):
    mon = datetime.date.fromisocalendar(iso[0], iso[1], 1)
    fri = datetime.date.fromisocalendar(iso[0], iso[1], 5)
    return f"{mon.month}/{mon.day}~{fri.month}/{fri.day}"

def carrot_for_dates(dates):
    """그 주 날짜의 강사(Carrot) 교정쌍 original→better."""
    out = []
    for f in sorted(glob.glob(os.path.join(CARROT, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for item in (d.get("data", {}) or {}).get("list", []) or []:
            if (item.get("createDate") or "")[:10] in dates:
                for sub in item.get("subList", []) or []:
                    o = (sub.get("original") or "").strip()
                    b = (sub.get("better") or "").strip()
                    if o and b and o.lower() != b.lower():
                        out.append((o, b))
    return out

def build_digest(week_rows, carrot_pairs):
    iso = week_rows[-1]["iso"]
    wl, wr = week_label(iso), week_range(iso)
    L = []
    L.append(f"# Weekly English Study Digest — {wl} ({wr})")
    L.append("")
    L.append("This is a study digest from my one-on-one English phone lessons this week. "
             "Please turn it into a friendly, encouraging two-host English podcast (Audio Overview) "
             "that reviews my mistakes, explains WHY the natural version is better, "
             "teaches the key vocabulary with example sentences, and ends with quick practice. "
             "Keep the level around A2–B1 and speak slowly and clearly.")
    L.append("")

    # 주제
    topics = [r.get("topic", "").strip() for r in week_rows if r.get("topic")]
    L.append("## Topics covered this week")
    for t in topics:
        L.append(f"- {t}")
    L.append("")

    # 문법 초점 / 약점
    gram = Counter((r.get("grammar_norm") or "?") for r in week_rows)
    L.append("## Grammar focus (most frequent weak points)")
    for g, c in gram.most_common():
        L.append(f"- {g} ({c}x)")
    L.append("")

    # 교정 (❌→✅)
    L.append("## Corrections — what I said vs. the natural version")
    n = 0
    for r in week_rows:
        for p in r.get("pairs", []):
            said = (p.get("said") or "").strip()
            nat = (p.get("natural") or "").strip()
            if said and nat:
                n += 1
                L.append(f'{n}. I said: "{said}"')
                L.append(f'   Natural: "{nat}"')
    if n == 0:
        L.append("(none recorded this week)")
    L.append("")

    # 강사 교정
    if carrot_pairs:
        L.append("## Tutor's official corrections")
        for i, (o, b) in enumerate(carrot_pairs, 1):
            L.append(f'{i}. "{o}"  ->  "{b}"')
        L.append("")

    # 어휘
    vseen, vocab = set(), []
    for r in week_rows:
        for v in r.get("vocab", []):
            w = (v.get("word") or "").strip()
            if w and w.lower() not in vseen:
                vseen.add(w.lower()); vocab.append(v)
    if vocab:
        L.append("## Key vocabulary")
        for v in vocab:
            w = v.get("word", ""); m = v.get("meaning", ""); pos = v.get("pos", "")
            L.append(f"- {w}" + (f" ({pos})" if pos else "") + (f" — {m}" if m else ""))
        L.append("")

    L.append("## Please cover in the podcast")
    L.append("- Pick my 1–2 most repeated mistakes and explain the rule with a memorable rule of thumb.")
    L.append("- Explain why Korean-influenced phrasing sounds unnatural and how English expresses it.")
    L.append("- Teach the vocabulary in real example sentences I could use at work.")
    L.append("- End with 3 quick recall questions.")
    L.append("")
    return wl, "\n".join(L)

def main():
    rows = load_rows()
    if not rows:
        print("no data"); return
    last_iso = rows[-1]["iso"]
    week_rows = [r for r in rows if r["iso"] == last_iso]
    dates = {r["date"] for r in week_rows}
    carrot_pairs = carrot_for_dates(dates)
    wl, text = build_digest(week_rows, carrot_pairs)
    dated = os.path.join(DOCS, f"digest-{wl}.txt")
    latest = os.path.join(DOCS, "digest-latest.txt")
    for path in (dated, latest):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    print(f"wrote {dated} and digest-latest.txt  week={wl} "
          f"lessons={len(week_rows)} carrot={len(carrot_pairs)} chars={len(text)}")

if __name__ == "__main__":
    main()

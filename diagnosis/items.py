"""
강사 교정 기준표 / tutor-correction reference table (DIAGNOSIS_PLAN 2절 '강사 항목 분류').

build  : docs/carrot 에서 표본 5일의 항목을 모아 종류(문법·어휘 / 발음 / 교정 없음)와
         틀린 부분·고친 부분 단어를 자동으로 제안 → .diag/carrot_items.json (draft)
keys   : 검토한 핵심 묶음을 넣는다 — .diag/carrot_keys.json {id: {"error": [...], "fix": [...]}}
         '빠뜨린 실수'(go back my office → go back to my office)도 잡히도록 연속된 단어 묶음으로 쓴다.
show   : 표를 사람이 읽기 좋게 출력 (검토용)
freeze : 검토가 끝났다고 표시 — 이후 변형판 실행이 허용된다. 고정 뒤에는 바꾸지 않는다(바꾸면 변경 기록).
실행: python3 -m diagnosis.items build|keys|show|freeze
"""
import glob
import json
import os
import sys
from datetime import datetime

from diagnosis.common import DIAG, KST, ROOT, SAMPLES, atomic_write_json, read_json, words

PATH = os.path.join(DIAG, "carrot_items.json")


def classify(original, better):
    """'grammar'(문법·어휘) / 'pron'(발음 메모) / 'none'(원문 = 고친 문장)."""
    if "pronounc" in (original + " " + better).lower():
        return "pron"
    if words(original) == words(better):
        return "none"
    return "grammar"


def key_tokens(original, better):
    """틀린 부분 = 원문에만 있는 단어, 고친 부분 = 고친 문장에만 있는 단어 (자동 제안 — 검토 대상)."""
    o, b = words(original), words(better)
    return [w for w in o if w not in set(b)], [w for w in b if w not in set(o)]


def build(carrot_dir=None):
    carrot_dir = carrot_dir or os.path.join(ROOT, "docs", "carrot")
    items = []
    for p in sorted(glob.glob(os.path.join(carrot_dir, "2026-*.json"))):
        for entry in json.load(open(p, encoding="utf-8")).get("data", {}).get("list", []):
            day = (entry.get("createDate") or "")[:10]
            if day not in SAMPLES:
                continue
            for i, sub in enumerate(entry.get("subList") or []):
                o, b = sub.get("original") or "", sub.get("better") or ""
                err, fix = key_tokens(o, b)
                items.append({"id": f"{day}#{i + 1}", "date": day, "kind": classify(o, b),
                              "original": o, "better": b, "suggest_error": err, "suggest_fix": fix,
                              "error_keys": [], "fix_keys": []})
    return {"frozen": False, "built_at": datetime.now(KST).isoformat(timespec="seconds"), "items": items}


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "show"
    if cmd == "build":
        old = read_json(PATH)
        if old and old.get("frozen"):
            raise SystemExit("❌ 이미 고정된 표 — 다시 만들지 않는다 (DIAGNOSIS_PLAN 변경 기록 후 수동으로 지울 것)")
        data = build()
        atomic_write_json(PATH, data)
        print(f"📝 초안 저장: {PATH}")
    data = read_json(PATH)
    if not data:
        raise SystemExit("❌ 표 없음 — build 먼저")
    if cmd == "keys":
        if data.get("frozen"):
            raise SystemExit("❌ 이미 고정된 표")
        keys = read_json(os.path.join(DIAG, "carrot_keys.json"), {})
        for i in data["items"]:
            if i["id"] in keys:
                i["error_keys"], i["fix_keys"] = keys[i["id"]]["error"], keys[i["id"]]["fix"]
        atomic_write_json(PATH, data)
        print(f"🔑 핵심 묶음 {len(keys)}개 반영")
    if cmd == "freeze":
        g = [i for i in data["items"] if i["kind"] == "grammar"]
        empty = [i["id"] for i in g if not i["error_keys"] or not i["fix_keys"]]
        if empty:
            raise SystemExit(f"❌ 핵심 단어가 빈 문법 항목: {empty} — 고친 뒤 freeze")
        data["frozen"], data["frozen_at"] = True, datetime.now(KST).isoformat(timespec="seconds")
        atomic_write_json(PATH, data)
        print("🔒 기준표 고정")
    kinds = {k: sum(i["kind"] == k for i in data["items"]) for k in ("grammar", "pron", "none")}
    print(f"항목 {len(data['items'])}개 — 문법·어휘 {kinds['grammar']} · 발음 {kinds['pron']} · 교정 없음 {kinds['none']}"
          f" · {'고정됨' if data.get('frozen') else '초안'}")
    if cmd == "show":
        for i in data["items"]:
            print(f"  {i['id']:<14} {i['kind']:<7} 틀림={i['error_keys'] or i['suggest_error']} 고침={i['fix_keys'] or i['suggest_fix']}")


if __name__ == "__main__":
    main(sys.argv)

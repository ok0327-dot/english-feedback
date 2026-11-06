"""
진단 입력 준비 / unpack and check the diagnosis inputs (DIAGNOSIS_PLAN 2절·7절).

사용자가 Drive '완료' 폴더에서 내려받은 zip(whisper_raw.jsonl + 녹음 5개)을 .diag/input 에 풀고,
① 표본 5건의 녹음·원본이 다 있는지 ② 강사 기록과 같은 수업인지(강사 원문 절반 이상이 그 날 원본에 토큰 겹침 ≥ 0.5)
를 **변형판을 돌리기 전에, 원본만으로** 확인한다. 못 넘는 날은 표본에서 바꿔야 한다(결과를 보고 고르지 않게).

실행: python3 -m diagnosis.prep [zip 경로]   (생략하면 Windows 다운로드 폴더의 가장 최근 drive-download*.zip)
"""
import glob
import json
import os
import sys
import zipfile

from diagnosis.common import ARCHIVE_NAME, INPUT, ROOT, SAMPLES, atomic_write_json, best_window, load_archive, words

DOWNLOADS = glob.glob("/mnt/c/Users/*/Downloads")


def find_zip():
    zips = [z for d in DOWNLOADS for z in glob.glob(os.path.join(d, "drive-download*.zip"))]
    return max(zips, key=os.path.getmtime) if zips else None


def unpack(zpath):
    os.makedirs(INPUT, exist_ok=True)
    wanted = set(SAMPLES.values()) | {ARCHIVE_NAME}
    got = []
    with zipfile.ZipFile(zpath) as z:
        for m in z.namelist():
            base = os.path.basename(m)
            if base in wanted:
                with z.open(m) as src, open(os.path.join(INPUT, base), "wb") as dst:
                    dst.write(src.read())
                got.append(base)
    return got


def carrot_originals(date, carrot_dir=None):
    out = []
    for p in glob.glob(os.path.join(carrot_dir or os.path.join(ROOT, "docs", "carrot"), "2026-*.json")):
        for e in json.load(open(p, encoding="utf-8")).get("data", {}).get("list", []):
            if (e.get("createDate") or "")[:10] == date:
                out += [s.get("original") or "" for s in e.get("subList") or []]
    return out


def match_ratio(originals, raw_text):
    """강사 원문 중 원본 전사에 비슷하게(겹침 ≥ 0.5) 나오는 비율."""
    ws = words(raw_text)
    hits = [o for o in originals if best_window(o, ws)[0] >= 0.5]
    return len(hits), len(originals)


def check():
    report, ok = {}, True
    arch_path = os.path.join(INPUT, ARCHIVE_NAME)
    arch = load_archive(arch_path) if os.path.exists(arch_path) else {}
    for date, fname in sorted(SAMPLES.items()):
        audio = os.path.join(INPUT, fname)
        size = os.path.getsize(audio) if os.path.exists(audio) else 0
        rec = arch.get(fname)
        hit, total = match_ratio(carrot_originals(date), rec["text"]) if rec else (0, 0)
        good = size > 1_000_000 and rec is not None and total and hit * 2 >= total
        ok &= bool(good)
        report[date] = {"audio_mb": round(size / 1e6, 1), "raw": bool(rec), "carrot_match": f"{hit}/{total}", "ok": bool(good)}
        print(f"{'✅' if good else '❌'} {date}: 녹음 {size / 1e6:.1f}MB · 원본 {'있음' if rec else '없음'} · 강사 원문 일치 {hit}/{total}")
    atomic_write_json(os.path.join(INPUT, "prep_report.json"), report)
    return ok


def main(argv):
    z = argv[1] if len(argv) > 1 else find_zip()
    if z:
        print(f"📦 {z} → {INPUT}: {', '.join(unpack(z)) or '(맞는 파일 없음)'}")
    else:
        print("ℹ️ zip 을 찾지 못함 — .diag/input 에 이미 있는 파일로 확인")
    if not check():
        raise SystemExit("❌ 준비 미완료 — 위 ❌ 날짜 확인 (없는 파일은 다시 받기, 일치 미달은 표본 교체 후 DIAGNOSIS_PLAN 변경 기록)")
    print("✅ 진단 입력 준비 완료")


if __name__ == "__main__":
    main(sys.argv)

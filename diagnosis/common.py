"""
0단계 진단 공용 도구 / shared helpers for the stage-0 diagnosis (DIAGNOSIS_PLAN.md).

산출물(원본 전사·녹음·판별 결과)은 전부 .diag/ 에만 둔다 — 공개 저장소라 커밋하지 않는다(.gitignore).
코드는 공개여도 된다: 수업 내용을 담지 않는다.
"""
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAG = os.environ.get("DIAG_DIR") or os.path.join(ROOT, ".diag")
INPUT = os.path.join(DIAG, "input")
OUT = os.path.join(DIAG, "out")
KST = timezone(timedelta(hours=9))

# 표본 5건 (DIAGNOSIS_PLAN 2절, 고정) — 수업일 → 녹음 파일명
SAMPLES = {
    "2026-09-21": "전화영어_025180304_20260921080013.m4a",
    "2026-10-05": "전화영어_025180304_20261005080045.m4a",
    "2026-10-06": "전화영어_025180304_20261006080029.m4a",
    "2026-10-07": "전화영어_025180304_20261007080016.m4a",
    "2026-10-08": "전화영어_025180304_20261008080106.m4a",  # 같은 날 33초 조각(…080016)은 아님
}
ARCHIVE_NAME = "whisper_raw.jsonl"

_WORD = re.compile(r"[a-z0-9']+")


def words(text):
    """비교용 단어 목록 — 소문자, 괄호 메모 제거(강사 기록의 '(pronounced REER)' 등), 화자 라벨 제거."""
    t = re.sub(r"\([^)]*\)|\[(?:tutor|student|\?[^\]]*|\?)\]", " ", (text or ""), flags=re.I)
    return _WORD.findall(t.lower().replace("’", "'"))


def best_window(needle, hay_words):
    """
    needle(문장)의 단어가 hay_words 의 어느 연속 구간에 가장 많이 들어 있는지.
    반환 (점수 0~1, 시작, 끝) — 점수 = 겹친 단어 수(중복 포함) / needle 단어 수.
    """
    n = words(needle)
    if not n or not hay_words:
        return 0.0, 0, 0
    need, size = Counter(n), len(n)
    best = (0.0, 0, 0)
    width = size + max(2, size // 3)  # 사이에 군말이 끼어도 잡히게 조금 넓게
    for i in range(0, max(1, len(hay_words) - size + 1)):
        win = hay_words[i:i + width]
        score = sum((Counter(win) & need).values()) / size
        if score > best[0]:
            best = (score, i, i + len(win))
            if score >= 1.0:
                break
    return best


def has_ngram(ws, phrase):
    """단어 목록 ws 안에 phrase(연속 단어 묶음)가 그대로 있는지."""
    p = words(phrase)
    if not p:
        return False
    return any(ws[i:i + len(p)] == p for i in range(len(ws) - len(p) + 1))


def load_archive(path):
    """whisper_raw.jsonl → {녹음 파일명: 기록}. 깨진 줄은 건너뛴다. 같은 녹음이 여럿이면 처음 것."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and rec.get("source_file") and rec["source_file"] not in out:
                out[rec["source_file"]] = rec
    return out


def sha(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]


def atomic_write_json(path, obj):
    """끝까지 쓴 뒤에 이름을 바꾼다 — 중간에 멈춰도 반쯤 쓴 결과가 '완료'로 보이지 않게."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def out_path(variant, date):
    return os.path.join(OUT, variant, f"{date}.json")


def manifest_add(entry):
    """실행 기록부 — 무엇을 언제 어떤 모델·지시문으로 돌렸는지 한 줄씩 (판정 때 섞이지 않게)."""
    os.makedirs(OUT, exist_ok=True)
    entry = dict(entry, at=datetime.now(KST).isoformat(timespec="seconds"))
    with open(os.path.join(OUT, "manifest.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def require_frozen_items():
    """강사 기준표가 고정되지 않았으면 변형판을 돌리지 않는다 (판정 기준을 결과보다 먼저 고정)."""
    items = read_json(os.path.join(DIAG, "carrot_items.json"))
    if not items or not items.get("frozen"):
        raise SystemExit("❌ 강사 기준표가 고정되지 않음 — python3 -m diagnosis.items build → 검토 → freeze 먼저")
    return items

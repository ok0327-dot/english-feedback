#!/usr/bin/env python3
"""
0단계 진단 도구 검사 / tests for diagnosis/ (네트워크 미사용, 실제 수업 내용 없음 — 강사 데이터는 이미 공개된 docs/carrot).
실행 / run:  python3 tests/test_diagnosis.py
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp()
os.environ["DIAG_DIR"] = TMP
for key in ("GOOGLE_CREDENTIALS", "GROQ_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.setdefault(key, "x")
os.environ["GEMINI_API_KEY"] = "fake"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from diagnosis import common as C  # noqa: E402
from diagnosis import items as I  # noqa: E402
from diagnosis import label as L  # noqa: E402
from diagnosis import measure as M  # noqa: E402
from diagnosis import prompts as P  # noqa: E402
from diagnosis import run_gemini as G  # noqa: E402


def main():
    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    # 공용
    check("단어: 괄호 메모·화자 라벨 제거", C.words("[Student] My REEL (pronounced REER) is ok") == ["my", "reel", "is", "ok"])
    hay = C.words("so uh I think that is depend on the product you know")
    check("겹침: 군말 사이에서도 찾음", C.best_window("I think that is depend on the product", hay)[0] == 1.0)
    check("묶음: 연속일 때만", C.has_ngram(hay, "is depend") and not C.has_ngram(hay, "depend is"))

    # 강사 기준표 — 실제 docs/carrot 로 25개 = 16/5/4
    data = I.build()
    kinds = [i["kind"] for i in data["items"]]
    check("기준표 25개 = 문법 16 · 발음 5 · 없음 4",
          len(kinds) == 25 and kinds.count("grammar") == 16 and kinds.count("pron") == 5 and kinds.count("none") == 4)
    C.atomic_write_json(I.PATH, data)
    try:
        I.main(["x", "freeze"])
        check("핵심 묶음 없이 고정 금지", False)
    except SystemExit:
        check("핵심 묶음 없이 고정 금지", True)
    try:
        C.require_frozen_items()
        check("고정 전 실행 금지", False)
    except SystemExit:
        check("고정 전 실행 금지", True)

    # 피드백 교정 줄 읽기 — 줄 형식 + 표 형식
    md = ("- ❌ 학습자 원문 (As Said): \"I think that is depend on the product\"\n"
          "- ✅ 자연스러운 표현 (Natural): I think that depends on the product\n\n"
          "| # | ❌ 원문 | ✅ 교정 |\n|---|---|---|\n| 1 | I'm not enjoy that shoes | I don't enjoy shopping for shoes |\n")
    pairs = M.correction_pairs(md)
    check("교정 줄·표 둘 다 읽음", len(pairs) == 2 and pairs[1][1].startswith("I don't enjoy"))

    item = {"original": "I think that is depend on the product", "better": "I think that depends on the product",
            "error_keys": ["is depend"], "fix_keys": ["depends on"]}
    check("M3: 잡음", M.m3_captured(item, pairs)[0] == "yes")
    check("M3: 고친 말이 없으면 못 잡음",
          M.m3_captured(item, [("I think that is depend on the product", "I think so")])[0] == "no")
    check("M7: 틀린 그대로 남음", M.m7_preserved(item, "[Student] I think that is depend on the product.") == "yes")
    check("M7: 고쳐짐", M.m7_preserved(item, "[Student] I think that depends on the product.") == "fixed")
    check("M7: 문장 없음", M.m7_preserved(item, "[Tutor] hello there how are you") == "missing")
    check("M4: 두 전사 모두에 없는 인용만 지어냄",
          M.m4_fabricated([("I love pizza very much", "x"), ("that is depend on the product", "y")],
                          "I think that is depend on the product", "I think that is depend on the product")
          == ["I love pizza very much"])
    check("M1: 기능어 바뀜 = 문법형", M.m1_changes("I go to the office", "I went to office")["grammar_like"] >= 1)

    # 개선 지시문 — 현행 규칙이 빠지고, 받아쓰기 화자 안내가 붙음
    segs = [{"start": 0.0, "end": 2.0, "text": "Hello Joey"}, {"start": 3.8, "end": 6.0, "text": "I go to Sapporo"}]
    imp = P.improved_clean("Hello Joey. I go to Sapporo.", segs)
    check("개선 보정: 학생 말 고치지 말 것 · 실수=학생 규칙 없음",
          "고치지 마세요" in imp and "영문법 실수가 있는 쪽이 [Student]" not in imp)
    check("개선 보정(V7): 목소리 화자 안내", "목소리로 나눈 화자" in P.improved_clean("A: hi", segs, diarized=True))
    check("개선 검증: 실수 여부 판단 금지", "실수 여부로 판단 금지" in P.improved_verify("[Tutor] hi"))

    # 실행 순서 — 판·수업을 섞되 매번 같다
    s1, s2 = G.schedule(), G.schedule()
    check("순서: 20건 · 고정 시드로 같음 · 판별로 몰리지 않음",
          len(s1) == 20 and s1 == s2 and [v for v, _ in s1[:5]] != ["V1"] * 5)

    # 조용한 실패 차단 — 현행 보정이 실패하면 원본을 돌려주지만, 실행기는 실패로 친다
    def boom(*a, **k):
        raise Exception("Gemini 하루 무료 한도 소진 [gemini-2.5-flash] → 다음 모델로")
    real = P.pl.gemini_request
    P.pl.gemini_request = boom
    try:
        G.run_one("V1", "2026-10-07", {"text": "hi", "segments": [], "source_file": "x.m4a"})
        check("조용한 실패 차단", False)
    except RuntimeError as e:
        check("조용한 실패 차단", "보정 실패" in str(e) and G.is_quota(e))
    finally:
        P.pl.gemini_request = real

    # 이어서 돌리기 — 결과가 있으면 건너뜀
    os.makedirs(os.path.join(C.OUT, "V1"), exist_ok=True)
    done = G.schedule()[0]
    C.atomic_write_json(C.out_path(*done), {"ok": 1})
    check("이어서 돌리기: 끝난 건 건너뜀", os.path.exists(C.out_path(*done)))

    # 30줄 고르기 — 세 갈래, 중복 없음, 시간 순
    segs = [{"id": k, "start": k * 3.0 + (1.6 if k % 4 == 0 else 0), "end": k * 3.0 + 2.8,
             "text": ("Joey how was it?" if k % 5 == 0 else "I went there last week"), "avg_logprob": -0.1 * (k % 7)}
            for k in range(120)]
    picks = L.select(segs)
    check("30줄: 30개 · 중복 없음 · 시간 순",
          len(picks) == 30 and len({p["start"] for p in picks}) == 30 and picks == sorted(picks, key=lambda p: p["start"]))
    check("30줄: 세 갈래 모두 포함", {p["why"] for p in picks} == {"화자 전환 후보", "호명·질문", "무작위"})
    flat = [{"id": k, "start": k * 3.0, "end": k * 3.0 + 2.5, "text": "I went there last week"} for k in range(60)]
    check("30줄: 한 갈래가 모자라도 30줄 채움", len(L.select(flat)) == 30)
    check("화자 찾기", L.speaker_of("I went there last week", "[Tutor] how was it\n[Student] I went there last week") == "Student")
    check("AUC", L.auc([-1.0, -0.9], [-0.1, -0.2]) == 1.0 and L.auc([], [1]) is None)

    # 업로드 삭제 확인 — 삭제 요청 성공 + 내 파일 목록에서 사라짐 (코덱스 리뷰 P1, 403 은 모호해서 단독 근거로 안 씀)
    from diagnosis import run_transcribe as R
    R_del, R_get = R.requests.delete, R.requests.get

    class Resp:
        def __init__(self, c, body=None):
            self.status_code, self._b = c, body or {}

        def json(self):
            return self._b

    def fake_get(listing, single=403):
        return lambda url, *a, **k: Resp(200, {"files": listing}) if url.endswith("/files") else Resp(single)
    try:
        R.requests.delete, R.requests.get = (lambda *a, **k: Resp(200)), fake_get([{"name": "files/x"}])
        check("삭제 확인: 목록에 남아 있으면 아님(403 이어도)", R.delete("files/x", "k") is False)
        R.requests.delete, R.requests.get = (lambda *a, **k: Resp(500)), fake_get([])
        check("삭제 확인: 삭제 요청 실패면 아님", R.delete("files/x", "k") is False)
        R.requests.delete, R.requests.get = (lambda *a, **k: Resp(200)), fake_get([], single=200)
        check("삭제 확인: 아직 조회되면 아님", R.delete("files/x", "k") is False)
        R.requests.delete, R.requests.get = (lambda *a, **k: Resp(200)), fake_get([{"name": "files/other"}])
        check("삭제 확인: 삭제 성공 + 목록에 없으면 없어짐", R.delete("files/x", "k") is True)
    finally:
        R.requests.delete, R.requests.get = R_del, R_get

    # V7 판 M4 는 V7 받아쓰기를 기준으로 (코덱스 리뷰 P2)
    C.atomic_write_json(C.out_path("V7ears", "2026-10-07"), {"text": "[00:01] Speaker A: Hi Joey.\nSpeaker B: I go Sapporo."})
    check("M4 기준: V7 은 받아쓰기 원문", "Speaker A" in M.source_text("V7", "2026-10-07", {}, "whisper"))
    check("M4 기준: V7′ 은 화자 표시 지운 받아쓰기", M.source_text("V7p", "2026-10-07", {}, "whisper") == "Hi Joey.\nI go Sapporo.")
    check("M4 기준: 그 밖은 Whisper", M.source_text("V1", "2026-10-07", {}, "whisper") == "whisper")

    from diagnosis import tasks as TK
    check("V7′: 화자·시각 표시 지우기",
          TK.strip_diarization("[00:01] Speaker A: Hi Joey.\n[00:03] Speaker B: I go to Sapporo.") == "Hi Joey.\nI go to Sapporo.")

    print(f"\n{'ALL PASS' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

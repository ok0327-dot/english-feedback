#!/usr/bin/env python3
"""
그림자판 비교 검사 / tests for docs/shadow-compare.js · docs/compare.html · 홈페이지 🌗 카드 (네트워크 미사용).
실행 / run:  python3 tests/test_compare.py      (node 필요 / needs node)
"""
import json
import os
import re
import subprocess
import sys
import tempfile

for key in ("GOOGLE_CREDENTIALS", "GROQ_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.setdefault(key, "x")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import process_lesson as pl  # noqa: E402

JS = os.path.join(ROOT, "docs", "shadow-compare.js")

NODE_CHECKS = r"""
const S = require(process.argv[1]);
const out = {};
const runs = [
  {slug:"2026-11-05", status:"done",   at:"2026-11-08T21:18:00+09:00"},
  {slug:"2026-11-06", status:"done",   at:"2026-11-08T21:22:00+09:00"},
  {slug:"2026-11-06", status:"done",   at:"2026-11-09T09:00:00+09:00"},
  {slug:"2026-11-07", status:"failed", at:"2026-11-08T20:00:00+09:00"},
  {slug:"2026-11-10", status:"no_raw", at:"2026-11-08T20:00:00+09:00"},
  {slug:"../evil",    status:"done",   at:"2026-11-01T00:00:00+09:00"},
].map(r => JSON.stringify(r)).join("\n") + "\n{broken json";
out.parsed = S.parseRuns(runs);
out.cardEarly = S.cardState(runs, Date.parse("2026-11-08T13:00:00Z"));   // KST 11-08 22:00
out.cardDueFew = S.cardState(runs, Date.parse("2026-11-21T15:00:00Z"));  // KST 11-22 00:00
const ten = Array.from({length: 10}, (_, i) => JSON.stringify({slug: "2026-11-" + String(10 + i), status: "done", at: "2026-11-09T21:00:00+09:00"})).join("\n");
out.cardTen = S.cardState(ten, Date.parse("2026-11-10T00:00:00Z"));
out.cardEmpty = S.cardState("", 0);
const slugs = Array.from({length: 10}, (_, i) => "2026-11-" + String(10 + i));
out.sides = slugs.map(S.shadowSide);
out.sideStable = S.shadowSide("2026-11-06") === S.shadowSide("2026-11-06");
const all = (pick) => Object.fromEntries(slugs.map((s, i) => [s, pick(s, i)]));
const flip = (x) => x === "A" ? "B" : "A";
out.t7 = S.tally(all((s, i) => i < 7 ? S.shadowSide(s) : flip(S.shadowSide(s))), slugs);
out.t6same = S.tally(all((s, i) => i < 6 ? S.shadowSide(s) : "same"), slugs);
out.tPartial = S.tally({[slugs[0]]: S.shadowSide(slugs[0]), [slugs[1]]: "junk"}, slugs);
out.tOther = S.tally(Object.assign(all((s) => S.shadowSide(s)), {"2099-01-01": "A"}), slugs);
console.log(JSON.stringify(out));
"""


def main():
    failures = []

    def check(label, cond):
        print(("PASS " if cond else "FAIL ") + label)
        if not cond:
            failures.append(label)

    # 1) 계산 함수 (node)
    r = subprocess.run(["node", "-e", NODE_CHECKS, JS], capture_output=True, text=True)
    check("node 로 계산 함수 실행", r.returncode == 0)
    o = json.loads(r.stdout or "{}")
    p = o.get("parsed", {})
    check("기록: done 만 · 중복 하나로 · 이상한 slug·깨진 줄 무시", p.get("slugs") == ["2026-11-05", "2026-11-06"])
    check("기록: 첫 완료 시각", p.get("firstAt") == "2026-11-08T21:18:00+09:00")
    ce = o.get("cardEarly", {})
    check("카드: 비교일 = 첫 완료 + 14일 · D-14 · 2/10", ce.get("due") == "2026-11-22" and ce.get("left") == 14
          and not ce.get("ready") and "D-14" in ce.get("text", "") and "2/10" in ce.get("text", ""))
    cd = o.get("cardDueFew", {})
    check("카드: 비교일(한국 시간 자정)에 10쌍 미만이면 '비교일이 됐어요' + 정식 판정 안내",
          cd.get("ready") and cd.get("left") == 0 and "비교일이 됐어요" in cd.get("text", "") and "2/10" in cd.get("text", ""))
    check("카드: 10쌍 모이면 비교일 전이라도 '지금 비교할 때'", o.get("cardTen", {}).get("ready") and "지금" in o["cardTen"]["text"])
    check("카드: 그림자판 없으면 기본 안내", not o.get("cardEmpty", {}).get("ready") and o["cardEmpty"]["due"] is None)
    sides = o.get("sides", [])
    check("A/B 배정: 수업마다 고정 · 한쪽으로만 몰리지 않음", o.get("sideStable") and set(sides) == {"A", "B"})
    t7 = o.get("t7", {})
    check("집계: 그림자판 7/10 → 합격", t7.get("shadow") == 7 and t7.get("main") == 3 and t7.get("complete") and t7.get("pass"))
    t6 = o.get("t6same", {})
    check("집계: '비슷'은 승리로 안 셈 (6승 4비슷 → 불합격)", t6.get("shadow") == 6 and t6.get("same") == 4 and not t6.get("pass"))
    tp = o.get("tPartial", {})
    check("집계: 이상한 표는 무시 · 10표 전엔 판정 없음", tp.get("voted") == 1 and not tp.get("complete") and not tp.get("pass"))
    check("집계: 비교 대상 밖 수업의 표는 안 셈", o.get("tOther", {}).get("voted") == 10)

    # 2) 홈페이지: 매일 다시 만들어도 카드가 남는다
    d = tempfile.mkdtemp()
    open(os.path.join(d, "2026-11-06.html"), "w").write("<html></html>")
    pl._update_index_page(d)
    idx = open(os.path.join(d, "index.html"), encoding="utf-8").read()
    check("홈페이지: 🌗 카드 → compare.html", 'id="shadow-card"' in idx and 'href="compare.html"' in idx)
    check("홈페이지: 계산 스크립트 + 카드 갱신 코드", '<script src="shadow-compare.js"></script>' in idx and "S.cardState(t)" in idx)
    check("홈페이지: 기존 목록 그대로", 'data-date="2026-11-06"' in idx and "hideReview" in idx)
    live = open(os.path.join(ROOT, "docs", "index.html"), encoding="utf-8").read()
    check("지금 사이트의 홈페이지에도 카드 반영", 'id="shadow-card"' in live)

    # 3) 하루 페이지 구조 — 비교 페이지가 꺼내는 블록이 정확히 하나씩
    page = pl.generate_review_page("[Tutor] Hi.\n[Student] Hello.", "## 피드백\n- 좋아요", "a.m4a", 1200, "2026년 11월 06일")
    check("하루 페이지 틀: div.feedback·div.transcript 각 1개",
          page.count('<div class="feedback"') == 1 and page.count('<div class="transcript"') == 1)
    feedback_block = page[page.find('<div class="feedback"'):page.find('<div id="tab-transcript"')]
    check("하루 페이지 틀: 피드백 블록 안에 스크립트·이벤트 없음",
          not re.search(r"<script|\son[a-z]+=|javascript:", feedback_block, re.I))
    check("하루 페이지 틀: 판을 알아볼 표시어 없음 (Claude/그림자/🌗)",
          not re.search(r"claude|그림자|🌗", feedback_block, re.I))

    # 4) 비교 페이지
    cmp_html = open(os.path.join(ROOT, "docs", "compare.html"), encoding="utf-8").read()
    check("비교 페이지: 계산 함수 사용 · 같은 블록 선택자", '<script src="shadow-compare.js"></script>' in cmp_html
          and '"div.feedback"' in cmp_html and '"div.transcript"' in cmp_html)
    check("비교 페이지: 끼워 넣기 전 소독 · 저장소 접근은 try/catch",
          "function clean" in cmp_html and "localStorage.getItem" in cmp_html and "try {" in cmp_html)
    check("비교 페이지: 정답은 공개 전까지 숨김 (배정은 공개 함수에서만 글자로)",
          cmp_html.count("그림자판 = ") == 1 and "function reveal" in cmp_html)
    check("생성기가 비교 파일을 하루 페이지로 착각하지 않음",
          not os.path.basename("compare.html").startswith("2") and not os.path.basename("shadow-compare.js").startswith("2"))

    print(f"\n{'ALL PASS' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

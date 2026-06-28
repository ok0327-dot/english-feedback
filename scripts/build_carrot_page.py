#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎓 강사 공식 피드백 페이지 생성기 / Carrot official (tutor-written) feedback page.

docs/carrot/YYYY-MM.json (Carrot allFeedback API 원본 응답)을 읽어
docs/carrot.html 한 장으로 렌더링한다. 월별·일자별 강사 서술(memo) + 교정쌍(❌→✅).

데이터 출처: https://homeapi.carrotenglish.com/app/myclass/allFeedback?searchYM=YYYY-MM
  (scripts/fetch_carrot_feedback.py 가 주간으로 갱신·저장)

CLI:  python3 scripts/build_carrot_page.py
"""
import glob, json, os, html, datetime
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
CARROT = os.path.join(DOCS, "carrot")


def esc(s):
    return html.escape(str(s or ""), quote=True)


def _clean(s):
    return (s or "").strip()


def load_days():
    """docs/carrot/*.json 들을 읽어 일자별 항목 리스트로 평탄화·정렬(최신순)."""
    days = []
    for f in sorted(glob.glob(os.path.join(CARROT, "*.json"))):
        try:
            j = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for it in (j.get("data") or {}).get("list") or []:
            date = _clean(it.get("createDate"))
            if not date:
                continue
            memo = _clean(it.get("memo"))
            pairs = []
            for s in it.get("subList") or []:
                o, b = _clean(s.get("original")), _clean(s.get("better"))
                tr = _clean(s.get("betterTrans"))
                if tr.lower() == "none":
                    tr = ""
                if o or b:
                    pairs.append({"original": o, "better": b, "trans": tr})
            days.append({"id": it.get("idxFeedback"), "date": date,
                         "memo": memo, "pairs": pairs})
    # 같은 (날짜,id) 중복 제거, 최신순
    seen, out = set(), []
    for d in sorted(days, key=lambda x: (x["date"], str(x["id"])), reverse=True):
        k = (d["date"], d["id"])
        if k in seen:
            continue
        seen.add(k)
        out.append(d)
    return out


CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Noto Sans KR',-apple-system,sans-serif;background:#0f0f13;color:#e4e4e7;line-height:1.7}
.header{background:linear-gradient(135deg,#2a1a0f,#3a2410,#7a3f0f);padding:42px 24px 30px;text-align:center;border-bottom:1px solid rgba(255,255,255,.06)}
.header h1{font-size:24px;color:#fff5e8;margin-bottom:8px}
.header .range{font-size:13px;color:#e0b080;letter-spacing:1px}
.nav{max-width:760px;margin:0 auto;padding:14px 20px 0;display:flex;justify-content:space-between;font-size:13px}
.nav a{color:#64748b;text-decoration:none;padding:6px 10px;border-radius:8px}
.nav a:hover{color:#fbbf24;background:#16161d}
.container{max-width:760px;margin:0 auto;padding:18px 20px 80px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px}
.stat{background:#16161d;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:16px 10px;text-align:center}
.stat .n{font-size:22px;font-weight:700;color:#fb923c}.stat .l{font-size:11px;color:#94a3b8;margin-top:4px}
.intro{background:#16161d;border:1px solid rgba(251,146,60,.18);border-radius:14px;padding:16px 18px;margin-bottom:20px;font-size:13px;color:#cbd5e1}
.intro b{color:#fbbf24}
.mhd{font-size:13px;color:#fb923c;font-weight:700;margin:22px 0 10px;border-bottom:1px solid rgba(255,255,255,.06);padding-bottom:6px}
.day{background:#16161d;border:1px solid rgba(255,255,255,.06);border-radius:16px;padding:20px;margin-bottom:16px}
.day .d{font-size:14px;color:#fbbf24;font-weight:700;margin-bottom:10px;display:flex;align-items:center;gap:8px}
.day .d .cnt{font-size:11px;color:#64748b;font-weight:400;margin-left:auto}
.memo{color:#cbd5e1;font-size:13.5px;background:#0f0f13;border-left:3px solid #fb923c;border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:14px;white-space:pre-wrap}
.pair{border-left:2px solid #334155;padding:7px 0 7px 14px;margin:9px 0}
.said{color:#fca5a5;font-size:13.5px;margin-bottom:3px}
.nat{color:#86efac;font-size:13.5px}
.trans{color:#94a3b8;font-size:12px;margin-top:2px}
.muted{color:#64748b;font-size:12px}
.foot{text-align:center;font-size:11px;color:#475569;margin-top:26px;line-height:1.8}
"""


def render(days, fetched_at=""):
    total_pairs = sum(len(d["pairs"]) for d in days)
    months = OrderedDict()
    for d in days:
        months.setdefault(d["date"][:7], []).append(d)

    body = ""
    for ym in sorted(months.keys(), reverse=True):
        y, m = ym.split("-")
        body += f'<div class="mhd">{y}년 {int(m)}월 · {len(months[ym])}일</div>'
        for d in months[ym]:
            pairs_html = "".join(
                f'<div class="pair"><div class="said">❌ {esc(p["original"])}</div>'
                f'<div class="nat">✅ {esc(p["better"])}</div>'
                + (f'<div class="trans">🇰🇷 {esc(p["trans"])}</div>' if p["trans"] else "")
                + "</div>"
                for p in d["pairs"]
            ) or '<div class="muted">이 날의 교정 항목 없음</div>'
            memo_html = f'<div class="memo">{esc(d["memo"])}</div>' if d["memo"] else ""
            body += (f'<div class="day"><div class="d">🗓 {esc(d["date"])}'
                     f'<span class="cnt">교정 {len(d["pairs"])}개</span></div>'
                     f'{memo_html}{pairs_html}</div>')

    sub = f"Carrot English 강사 직접 작성 · {fetched_at} 기준" if fetched_at else "Carrot English 강사 직접 작성"
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><link rel="manifest" href="manifest.webmanifest"><meta name="theme-color" content="#0f0f13"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="당근영어"><link rel="apple-touch-icon" href="apple-touch-icon.png"><link rel="icon" type="image/png" sizes="192x192" href="icon-192.png"><script src="install-banner.js" defer></script><script src="sw-reg.js" defer></script>
<title>🎓 강사 공식 피드백</title><style>{CSS}</style></head><body>
<div class="header"><h1>🎓 강사 공식 피드백</h1>
<div class="range">{esc(sub)}</div></div>
<div class="nav"><a href="index.html">← 일일 복습</a><a href="review-index.html">📊 주간 복습 →</a></div>
<div class="container">
  <div class="stats">
    <div class="stat"><div class="n">{len(days)}</div><div class="l">강사 피드백 일수</div></div>
    <div class="stat"><div class="n">{total_pairs}</div><div class="l">강사 교정 항목</div></div>
    <div class="stat"><div class="n">{len(months)}</div><div class="l">수집 월</div></div>
  </div>
  <div class="intro">이 페이지는 <b>Carrot English 강사님이 매 수업 직접 작성</b>한 공식 피드백입니다.
  AI 피드백(일일 복습)과 <b>함께 보면</b> 같은 약점을 다른 관점에서 짚어줘 학습 효과가 큽니다.
  매주 자동 갱신됩니다.</div>
  {body or '<div class="muted">아직 수집된 강사 피드백이 없습니다.</div>'}
  <div class="foot">데이터: Carrot English allFeedback · scripts/build_carrot_page.py<br>
  매주 자동 갱신 · 강사 직접 작성 원문</div>
</div></body></html>"""


def build():
    days = load_days()
    fetched_at = ""
    meta_f = os.path.join(CARROT, "_fetched.txt")
    if os.path.exists(meta_f):
        fetched_at = open(meta_f, encoding="utf-8").read().strip()
    page = render(days, fetched_at)
    open(os.path.join(DOCS, "carrot.html"), "w", encoding="utf-8").write(page)
    print(f"✅ docs/carrot.html 생성 · {len(days)}일 · 교정 {sum(len(d['pairs']) for d in days)}개")


if __name__ == "__main__":
    build()

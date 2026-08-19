#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎓 강사 공식 피드백 페이지 생성기 / Carrot official (tutor-written) feedback page.

docs/carrot/YYYY-MM.json (Carrot allFeedback API 원본 응답)을 읽어
docs/carrot.html 한 장으로 렌더링한다. 월별·일자별 강사 서술(memo) + 교정쌍(❌→✅).

데이터 출처: https://homeapi.carrotenglish.com/app/myclass/allFeedback?searchYM=YYYY-MM
  (scripts/fetch_carrot_feedback.py 가 주간으로 갱신·저장)

신선도(staleness) 감시 / freshness monitoring:
  수집 워크플로우가 조용히 죽어도 사용자가 알 수 없던 문제를 막기 위해,
  마지막 갱신일을 페이지에 data-fetched-at 으로 심고 **브라우저에서 볼 때마다**
  경과일을 다시 계산해 배너를 띄운다.
  (정적 페이지라 빌드 시점에 계산해 두면 시간이 지나며 거짓말이 된다.)
  The stale-data banner is computed at view time, not at build time.

CLI:  python3 scripts/build_carrot_page.py
"""
import glob, json, os, re, html, datetime
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
CARROT = os.path.join(DOCS, "carrot")

KST = datetime.timezone(datetime.timedelta(hours=9))

# 신선도 임계값(일) / staleness thresholds in days
WARN_DAYS = 10   # 10~20일 = 주황 경고 / orange warning
BAD_DAYS = 21    # 21일 이상 = 빨강 경고 / red alert


def esc(s):
    return html.escape(str(s or ""), quote=True)


def _clean(s):
    return (s or "").strip()


def _data_files():
    """실제 피드백 데이터 파일만(_meta.json 등 메타파일 제외) / data files, excluding meta files."""
    return [f for f in sorted(glob.glob(os.path.join(CARROT, "*.json")))
            if not os.path.basename(f).startswith("_")]


def load_days():
    """docs/carrot/*.json 들을 읽어 일자별 항목 리스트로 평탄화·정렬(최신순)."""
    days = []
    for f in _data_files():
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


def read_freshness():
    """마지막 갱신일을 (YYYY-MM-DD, 출처, 추정여부) 로 반환 / last-fetch date, source, estimated?

    우선순위 / precedence:
      1) docs/carrot/_meta.json  → fetched_at (수집기가 남기는 공식 기록)
      2) docs/carrot/_fetched.txt → 한 줄 YYYY-MM-DD (기존 호환 / legacy)
      3) docs/carrot/*.json mtime 최신값 → '추정(estimated)' 표기
    셋 다 없으면 ("", "", False) → 배너는 '수집 기록 없음'(빨강)으로 처리.
    """
    meta_j = os.path.join(CARROT, "_meta.json")
    if os.path.exists(meta_j):
        try:
            m = json.load(open(meta_j, encoding="utf-8"))
            v = _clean(m.get("fetched_at"))
            if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                return v, "_meta.json", False
        except Exception:
            pass

    txt = os.path.join(CARROT, "_fetched.txt")
    if os.path.exists(txt):
        try:
            v = _clean(open(txt, encoding="utf-8").read())
            if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                return v, "_fetched.txt", False
        except Exception:
            pass

    # fallback: 데이터 파일 mtime 중 최신값(추정) / newest data-file mtime, estimated
    mtimes = [os.path.getmtime(f) for f in _data_files()]
    if mtimes:
        d = datetime.datetime.fromtimestamp(max(mtimes), KST).strftime("%Y-%m-%d")
        return d, "파일 수정시각", True
    return "", "", False


def _month_iter(start_ym, end_ym):
    """'YYYY-MM' 두 지점 사이의 모든 달 생성(양끝 포함) / inclusive month range."""
    y, m = int(start_ym[:4]), int(start_ym[5:7])
    ey, em = int(end_ym[:4]), int(end_ym[5:7])
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m > 12:
            y, m = y + 1, 1


def missing_months(days, today=None):
    """첫 수집월 ~ 이번 달 사이에서 **데이터가 한 건도 없는 달** 목록.

    수집 실패가 누적되면 그 달은 영구히 비게 되므로 구멍을 눈에 보이게 만든다.
    Returns month gaps between the first collected month and the current month.
    """
    have = sorted({d["date"][:7] for d in days if len(d["date"]) >= 7})
    if not have:
        return []
    now = today or datetime.datetime.now(KST)
    cur = now.strftime("%Y-%m")
    hs = set(have)
    return [ym for ym in _month_iter(have[0], max(cur, have[-1])) if ym not in hs]


def fetched_months():
    """마지막 수집 실행이 실제로 받아온 월 / months the last successful run actually fetched.

    `_meta.json` 의 `months` (수집기가 기록). 여기에 있는데도 데이터가 0건이면
    '수집 실패로 빈 달'이 아니라 '수업이 없어서 빈 달'이므로 경보를 올리지 않는다.
    """
    try:
        m = json.load(open(os.path.join(CARROT, "_meta.json"), encoding="utf-8"))
        return {str(x) for x in (m.get("months") or [])}
    except Exception:
        return set()


def recent_month_gaps(gaps, today=None, fetched=None):
    """누락 월 중 **이번 달·지난 달**에 해당하는 것 / gaps that fall in the current or previous month.

    파일 mtime 추정치는 git checkout 시각에 오염될 수 있으므로(체크아웃하면 늘 '오늘'),
    최근 달이 통째로 비었는지는 날짜와 독립적으로 검사해 배너를 강제로 빨강으로 올린다.
    단, 수집기가 그 달을 실제로 받아왔다면(=`_meta.json` 의 `months` 에 있음) 진짜 '수업 없는 달'
    이므로 제외한다 — 그러지 않으면 새 달 1~2일차에 늘 거짓 경보가 뜬다.
    Months the fetcher really did pull are excluded to avoid a false alarm at the
    start of every month.
    """
    now = today or datetime.datetime.now(KST)
    cur = now.strftime("%Y-%m")
    py, pm = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
    prev = f"{py:04d}-{pm:02d}"
    done = fetched_months() if fetched is None else fetched
    return [g for g in gaps if g in (cur, prev) and g not in done]


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
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px}
.stat{background:#16161d;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:16px 10px;text-align:center}
.stat .n{font-size:22px;font-weight:700;color:#fb923c}
.stat .n.sm{font-size:13.5px;line-height:1.5;padding-top:4px}
.stat .l{font-size:11px;color:#94a3b8;margin-top:4px}
@media(max-width:520px){.stats{grid-template-columns:repeat(2,1fr)}}
.fresh{display:none;border-radius:14px;padding:13px 16px;margin-bottom:16px;font-size:13px;line-height:1.65;border:1px solid transparent}
.fresh.show{display:block}
.fresh b{font-weight:700}
.fresh .sub{font-size:11.5px;opacity:.85;margin-top:5px}
.fresh.ok{background:rgba(34,197,94,.07);border-color:rgba(34,197,94,.22);color:#86efac}
.fresh.warn{background:rgba(251,146,60,.10);border-color:rgba(251,146,60,.40);color:#fdba74}
.fresh.bad{background:rgba(248,113,113,.10);border-color:rgba(248,113,113,.45);color:#fca5a5}
.gap{background:rgba(251,146,60,.07);border:1px dashed rgba(251,146,60,.38);border-radius:14px;padding:12px 16px;margin-bottom:18px;font-size:12.5px;color:#fdba74}
.gap .ms{color:#fbbf24;font-weight:700}
.gap .sub{display:block;font-size:11.5px;color:#94a3b8;margin-top:4px}
.gap code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:#cbd5e1;background:#0f0f13;border-radius:5px;padding:1px 5px}
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

# 뷰 시점 기준 신선도 계산 / freshness recomputed in the browser on every view —
# 빌드 때 계산해 두면 몇 주 뒤에는 틀린 숫자를 보여주게 된다.
JS = r"""
(function(){
  var el=document.getElementById('fresh');
  if(!el)return;
  var at=el.getAttribute('data-fetched-at')||'';
  var est=el.getAttribute('data-estimated')==='1';
  var src=el.getAttribute('data-source')||'';
  var msg=el.querySelector('.msg'), sub=el.querySelector('.sub');
  // 최근 달(이번달·지난달)이 통째로 비어 있으면 날짜와 무관하게 빨강 / recent empty months = hard alarm.
  // 파일 mtime 추정치는 git checkout 시각에 오염될 수 있어 이 검사가 최후의 안전장치다.
  var rg=(el.getAttribute('data-recent-gaps')||'').split(',').filter(Boolean);
  if(rg.length){
    el.className='fresh bad show';
    msg.innerHTML='⚠️ <b>최근 '+rg.length+'개월치 강사 피드백이 비어 있습니다</b> ('+rg.join(', ')+') — 수집 워크플로우를 확인하세요.';
    sub.textContent='마지막 갱신 '+(at||'기록 없음')+(est?' (추정)':'')+(src?' · 출처: '+src:'');
    return;
  }
  if(!/^\d{4}-\d{2}-\d{2}$/.test(at)){
    el.className='fresh bad show';
    msg.innerHTML='⚠️ <b>강사 피드백 수집 기록이 없습니다</b> — 수집 워크플로우를 확인하세요.';
    sub.textContent='docs/carrot/_meta.json · _fetched.txt 둘 다 없음';
    return;
  }
  // KST(+09:00) 자정 기준 경과일 / days elapsed, anchored to KST midnight
  var n=Math.floor((Date.now()-Date.parse(at+'T00:00:00+09:00'))/86400000);
  if(n<0)n=0;
  if(n>20){
    el.className='fresh bad show';
    msg.innerHTML='⚠️ <b>강사 피드백이 '+n+'일째 갱신되지 않았습니다</b> — 수집 워크플로우를 확인하세요.';
  }else if(n>=10){
    el.className='fresh warn show';
    msg.innerHTML='⚠️ 강사 피드백이 <b>'+n+'일째</b> 갱신되지 않았습니다 — 수집 워크플로우를 확인하세요.';
  }else{
    el.className='fresh ok show';
    msg.innerHTML='✅ 최신 상태 · '+(n===0?'오늘':n+'일 전')+' 갱신';
  }
  sub.textContent='마지막 갱신 '+at+(est?' (추정)':'')+(src?' · 출처: '+src:'');
})();
"""


def render(days, fetched_at="", source="", estimated=False, gaps=None):
    gaps = gaps or []
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

    # 신선도 배너 자리(내용·색은 JS가 뷰 시점에 채움) / placeholder filled by JS at view time
    recent_gaps = recent_month_gaps(gaps)
    fresh_html = (f'<div class="fresh" id="fresh" data-fetched-at="{esc(fetched_at)}"'
                  f' data-source="{esc(source)}" data-estimated="{"1" if estimated else "0"}"'
                  f' data-recent-gaps="{esc(",".join(recent_gaps))}">'
                  f'<div class="msg"></div><div class="sub"></div></div>')

    # 월 커버리지 구멍 / month coverage gaps
    gap_html = ""
    if gaps:
        gap_html = ('<div class="gap">🕳 누락된 달: <span class="ms">'
                    + esc(", ".join(gaps))
                    + '</span><span class="sub">해당 월은 강사 피드백이 한 건도 수집되지 않았습니다. '
                      '백필 / backfill: <code>python3 scripts/fetch_carrot_feedback.py --backfill</code>'
                      '</span></div>')

    last = (f"{fetched_at}{' (추정)' if estimated else ''}") if fetched_at else "기록 없음"
    sub = (f"Carrot English 강사 직접 작성 · 마지막 갱신 {last}" if fetched_at
           else "Carrot English 강사 직접 작성 · 갱신 기록 없음")
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><link rel="manifest" href="manifest.webmanifest"><meta name="theme-color" content="#0f0f13"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="당근영어"><link rel="apple-touch-icon" href="apple-touch-icon.png"><link rel="icon" type="image/png" sizes="192x192" href="icon-192.png"><script src="install-banner.js" defer></script><script src="sw-reg.js" defer></script>
<title>🎓 강사 공식 피드백</title><style>{CSS}</style></head><body>
<div class="header"><h1>🎓 강사 공식 피드백</h1>
<div class="range">{esc(sub)}</div></div>
<div class="nav"><a href="index.html">← 일일 복습</a><a href="review-index.html">📊 주간 복습 →</a></div>
<div class="container">
  {fresh_html}
  <div class="stats">
    <div class="stat"><div class="n">{len(days)}</div><div class="l">강사 피드백 일수</div></div>
    <div class="stat"><div class="n">{total_pairs}</div><div class="l">강사 교정 항목</div></div>
    <div class="stat"><div class="n">{len(months)}</div><div class="l">수집 월</div></div>
    <div class="stat"><div class="n sm">{esc(last)}</div><div class="l">마지막 갱신</div></div>
  </div>
  {gap_html}
  <div class="intro">이 페이지는 <b>Carrot English 강사님이 매 수업 직접 작성</b>한 공식 피드백입니다.
  AI 피드백(일일 복습)과 <b>함께 보면</b> 같은 약점을 다른 관점에서 짚어줘 학습 효과가 큽니다.
  매주 월요일 자동 갱신되며, <b>갱신이 멈추면 위에 경고 배너</b>가 표시됩니다.</div>
  {body or '<div class="muted">아직 수집된 강사 피드백이 없습니다.</div>'}
  <div class="foot">데이터: Carrot English allFeedback · scripts/build_carrot_page.py<br>
  매주 자동 갱신 · 강사 직접 작성 원문</div>
</div>
<script>{JS}</script>
</body></html>"""


def build():
    days = load_days()
    fetched_at, source, estimated = read_freshness()
    gaps = missing_months(days)
    page = render(days, fetched_at, source, estimated, gaps)
    open(os.path.join(DOCS, "carrot.html"), "w", encoding="utf-8").write(page)

    print(f"✅ docs/carrot.html 생성 · {len(days)}일 · 교정 {sum(len(d['pairs']) for d in days)}개")
    if fetched_at:
        age = (datetime.datetime.now(KST).date()
               - datetime.date(*map(int, fetched_at.split("-")))).days
        tag = "🔴" if age >= BAD_DAYS else ("🟠" if age >= WARN_DAYS else "🟢")
        note = f"추정·{source}" if estimated else source
        print(f"{tag} 마지막 갱신 {fetched_at} ({note}) · {age}일 경과")
    else:
        print("🔴 갱신 기록 없음(_meta.json / _fetched.txt 부재) — 수집 워크플로우 확인 필요")
    if gaps:
        print(f"🕳 누락된 달: {', '.join(gaps)}")
        rg = recent_month_gaps(gaps)
        if rg:
            print(f"🔴 최근 달({', '.join(rg)})이 비어 있음 — 배너는 갱신일과 무관하게 빨강으로 표시됩니다")


if __name__ == "__main__":
    build()

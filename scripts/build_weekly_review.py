#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
주간 복습 스냅샷 생성기 (모델 B) / Weekly review snapshot generator.

docs/ 의 일일 피드백을 ISO 주차로 묶어, 주마다 자기완결형 스냅샷을 만든다.
  docs/review-2026-Www.html  ← 주마다 1개 ("이번 주" + "누적 추세" + "종합")
  docs/review-index.html      ← 허브 (전체 누적 요약 + 주간 목록)

설계 / Design:
  - 각 주간 파일은 그 주 수업 + (CUTOFF~그 주말까지) 누적을 함께 담아 자기완결적.
  - 종합문(synthesis)은 규칙기반으로 항상 채워져 파일이 절대 깨지지 않는다.
    → 클라우드 /schedule 루틴의 Claude가 <div id="synthesis"> 내용을 더 좋은
      통찰로 교체하도록 설계됨(없어도 동작, 있으면 품질↑).
  - Gemini 미사용(순수 집계). Gemini 무료 쿼터 0 소모.

CLI:
  python3 scripts/build_weekly_review.py            # 전체 주차 생성
  실행 시 stdout 마지막 줄에 CURRENT_WEEK_FILE=... 출력 (루틴이 현재 주를 식별).
"""
import glob, re, os, html, json, datetime
from collections import Counter, OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
CUTOFF = "2026-05-08"   # 개선된 프롬프트 시작점 (이전은 문법 진단이 '관사' 고정)

# ───────────────────────── 파싱 / parsing ─────────────────────────
def clean(s):
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def grammar_label(seg):
    s = clean(seg)
    s = re.sub(r"\(Target Grammar\)", "", s)
    s = re.sub(r"Category\s*[:：]", "", s)
    s = re.sub(r"^[^A-Za-z가-힣]+", "", s)
    m = re.search(r'([A-Z][A-Za-z0-9\-\'"/&,\.\s]{2,55}?\s*\([^)]*\))', s)
    if m: return clean(m.group(1))
    m = re.search(r'([A-Z][A-Za-z0-9\-\'"/&,\. ]{4,55}?)(?=\s*(?:Joey|학습자|이번|오늘|님|[가-힣]))', s)
    if m: return clean(m.group(1))
    return clean(s[:45])

def norm_grammar(g):
    g = re.sub(r"\([^)]*\)", "", g).strip().lower()
    if "article" in g: return "Articles (a/an/the)"
    if "preposition" in g: return "Prepositions"
    if "subject-verb" in g or "agreement" in g: return "Subject–Verb Agreement"
    if "auxiliary" in g or "verb form" in g: return "Verb Forms / Auxiliaries"
    if "tense" in g: return "Verb Tense"
    if "missing subject" in g: return "Missing Subjects / Verbs"
    if "gerund" in g or "noun phrase" in g or "동명사" in g: return "Gerunds / Noun Phrases"
    if "determiner" in g or "quantifier" in g: return "Determiners / Quantifiers"
    if "causative" in g: return 'Causative "get"'
    return g.title() or "기타"

def parse_lesson(f):
    t = re.sub(r"<style.*?</style>", " ", open(f, encoding="utf-8").read(), flags=re.S)
    t = re.sub(r"<script.*?</script>", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t); t = html.unescape(t); t = re.sub(r"[ \t]+", " ", t)
    date = os.path.basename(f)[:10]
    if "한 놈만 패기" not in t or "유창성 업그레이드" not in t:
        return None  # 깨진 대용량 파일 자동 제외
    mt = re.search(r"Topic[:：]\s*([^\n]{3,90})", t)
    topic = clean(mt.group(1)) if mt else ""
    mg = re.search(r"한 놈만 패기(.{0,300})", t, re.S)
    grammar = grammar_label(mg.group(1)) if mg else ""
    ms = re.search(r"유창성 점수[^0-9]{0,12}([0-9]+(?:\.[0-9])?)\s*/\s*10", t)
    score = float(ms.group(1)) if ms else None
    fl = re.search(r"유창성 업그레이드(.*?)(?:한 놈만 패기|어휘 확장)", t, re.S)
    fseg = fl.group(1) if fl else ""
    said = re.findall(r'❌[^"]*"([^"]+)"', fseg)
    nat  = re.findall(r'✅[^"]*"([^"]+)"', fseg)
    pairs = [{"said": clean(said[i]), "natural": clean(nat[i] if i < len(nat) else "")}
             for i in range(len(said)) if said[i].strip() and (nat[i] if i < len(nat) else "")]
    vb = re.search(r"어휘 확장(.*?)(?:실전 복습|자신감 충전|성과 지표|$)", t, re.S)
    vseg = vb.group(1) if vb else ""
    vocab = [{"word": clean(m.group(1)), "pos": clean(m.group(3)), "meaning": clean(m.group(4))}
             for m in re.finditer(
                 r"\d+\.\s+([A-Za-z][A-Za-z\-]+(?:\s[A-Za-z\-]+){0,2})\s*/([^/]*)/\s*\(([^)]+)\)\s*\*?\s*뜻[:：]\s*([^*\n]+)",
                 vseg)]
    y, m_, d_ = map(int, date.split("-"))
    iso = datetime.date(y, m_, d_).isocalendar()
    return {"date": date, "iso": (iso[0], iso[1]), "topic": topic, "grammar": grammar,
            "grammar_norm": norm_grammar(grammar), "score": score, "pairs": pairs, "vocab": vocab}

def load_all():
    files = sorted(f for f in glob.glob(os.path.join(DOCS, "2026-*.html"))
                   if os.path.basename(f)[:10] >= CUTOFF)
    out = [parse_lesson(f) for f in files]
    return [l for l in out if l]

# ───────────────────────── 집계 헬퍼 / helpers ─────────────────────────
def week_label(iso): return f"{iso[0]}-W{iso[1]:02d}"
def week_file(iso):  return f"review-{week_label(iso)}.html"
def week_range(iso):
    mon = datetime.date.fromisocalendar(iso[0], iso[1], 1)
    fri = datetime.date.fromisocalendar(iso[0], iso[1], 5)
    return f"{mon.month}/{mon.day}~{fri.month}/{fri.day}"
def avg_score(ls):
    s = [l["score"] for l in ls if l["score"] is not None]
    return (sum(s) / len(s)) if s else 0
def dedup_vocab(ls):
    seen, out = set(), []
    for l in ls:
        for v in l["vocab"]:
            k = v["word"].lower()
            if k not in seen: seen.add(k); out.append(v)
    return out

def iso_ordinal(iso): return iso[0] * 53 + iso[1]   # (year,week) → 비교용 정수

def vocab_index(ls):
    """누적 단어를 dedup하되 등장횟수(count)·최근 주차(last_iso) 보존."""
    idx = OrderedDict()
    for l in ls:                                    # ls 는 날짜 오름차순
        for v in l["vocab"]:
            k = v["word"].lower()
            if k not in idx:
                idx[k] = {**v, "count": 0, "last_iso": l["iso"]}
            idx[k]["count"] += 1
            idx[k]["last_iso"] = l["iso"]            # 마지막 할당 = 가장 최근
    return list(idx.values())

VBUCKET = {0: "🔥 이번 주 신규", 1: "📅 최근 3주", 2: "🗂 그 이전"}

def rule_synthesis(week_ls, cum_ls):
    """규칙기반 종합문 (루틴의 Claude가 더 나은 통찰로 교체 가능).
    누적 약점 Top2 + 이번 주 유창성 추세(상승/정체/하락) + 다음 주 액션을 담는다."""
    gfreq = Counter(l["grammar_norm"] for l in cum_ls).most_common()
    top2 = gfreq[:2]
    top_str = ", ".join(f"{esc(k)}({v}회)" for k, v in top2) or "—"
    top1 = top2[0][0] if top2 else "—"
    wk_focus = ", ".join(sorted({l["grammar_norm"] for l in week_ls})) or "—"
    avg = avg_score(cum_ls)
    wk_avg = avg_score(week_ls)
    # 이번 주 평균 vs 누적 평균으로 추세 방향 판정 (±0.3 이내는 정체)
    if wk_avg and avg:
        diff = wk_avg - avg
        if diff >= 0.3:
            trend = f"이번 주 평균 <b>{wk_avg:.1f}</b>로 누적({avg:.1f}) 대비 <b>상승 📈</b>"
        elif diff <= -0.3:
            trend = f"이번 주 평균 <b>{wk_avg:.1f}</b>로 누적({avg:.1f}) 대비 <b>하락 📉 — 점검 필요</b>"
        else:
            trend = f"이번 주 평균 <b>{wk_avg:.1f}</b>로 누적({avg:.1f})과 <b>비슷한 정체</b>"
    else:
        trend = f"누적 유창성 평균 <b>{avg:.1f}/10</b>"
    return (f"이번 주 <b>{len(week_ls)}회</b> 수업의 문법 초점은 <b>{esc(wk_focus)}</b>입니다. "
            f"컷오프({CUTOFF}) 이후 누적 <b>{len(cum_ls)}회</b> 기준 가장 끈질긴 약점은 "
            f"<b>{top_str}</b>이고, {trend}입니다. "
            f"다음 주는 특히 <b>{esc(top1)}</b>를 의식하며 한 문장씩 또박또박 말해 보세요.")

# ───────────────────────── HTML ─────────────────────────
def esc(s): return html.escape(str(s), quote=True)

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Noto Sans KR',-apple-system,sans-serif;background:#0f0f13;color:#e4e4e7;line-height:1.7}
.header{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);padding:42px 24px 30px;text-align:center;border-bottom:1px solid rgba(255,255,255,.06)}
.header h1{font-size:24px;color:#f1f5f9;margin-bottom:8px}
.header .range{font-size:13px;color:#94a3b8;letter-spacing:2px}
.nav{max-width:760px;margin:0 auto;padding:14px 20px 0;display:flex;justify-content:space-between;font-size:13px}
.nav a{color:#64748b;text-decoration:none;padding:6px 10px;border-radius:8px}
.nav a:hover{color:#38bdf8;background:#16161d}
.container{max-width:760px;margin:0 auto;padding:18px 20px 80px}
.card{background:#16161d;border:1px solid rgba(255,255,255,.06);border-radius:16px;padding:22px;margin-bottom:20px}
.card h2{font-size:16px;color:#f1f5f9;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.card h2 .sub{font-size:12px;color:#64748b;font-weight:400;margin-left:auto}
.muted{color:#64748b;font-size:12px}.syn{color:#cbd5e1;font-size:14px}.syn b{color:#f1f5f9}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px}
.stat{background:#16161d;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:16px 10px;text-align:center}
.stat .n{font-size:22px;font-weight:700;color:#38bdf8}.stat .l{font-size:11px;color:#94a3b8;margin-top:4px}
.bar-row{display:flex;align-items:center;gap:10px;margin:8px 0}
.bar-label{width:160px;font-size:12.5px;color:#cbd5e1;text-align:right;flex-shrink:0}
.bar-track{flex:1;background:#0f0f13;border-radius:6px;height:20px;overflow:hidden}
.bar-fill{height:100%;background:linear-gradient(90deg,#3b82f6,#818cf8);border-radius:6px}
.bar-fill.hot{background:linear-gradient(90deg,#f43f5e,#fb7185)}
.bar-val{width:34px;font-size:12px;color:#94a3b8;flex-shrink:0}
.lesson{border-left:2px solid #334155;padding:6px 0 6px 14px;margin:10px 0}
.lesson .d{font-size:12px;color:#7dd3fc;font-weight:600}
.lesson .g{font-size:12px;color:#fbbf24;margin:2px 0}
.lesson .t{font-size:12.5px;color:#94a3b8}
.pair{border-left:2px solid #334155;padding:7px 0 7px 14px;margin:9px 0}
.said{color:#fca5a5;font-size:13px;margin-bottom:3px}.nat{color:#86efac;font-size:13px}
.deck{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:9px}
/* 표준 3D 플립: .vinner 래퍼만 회전(모바일 안정) / robust 3D flip via inner wrapper */
.vcard{height:80px;cursor:pointer;perspective:700px;-webkit-tap-highlight-color:transparent}
.vinner{position:relative;width:100%;height:100%;transition:transform .45s;transform-style:preserve-3d;-webkit-transform-style:preserve-3d}
.vcard.flipped .vinner{transform:rotateY(180deg);-webkit-transform:rotateY(180deg)}
.vfront,.vback{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:8px;text-align:center;border-radius:11px;border:1px solid rgba(255,255,255,.07);-webkit-backface-visibility:hidden;backface-visibility:hidden}
.vfront{background:#0f0f13;gap:3px}.vword{font-size:14px;font-weight:600;color:#f1f5f9}.vpos{font-size:10px;color:#64748b}
.vback{background:#1e293b;color:#7dd3fc;font-size:12.5px;transform:rotateY(180deg);-webkit-transform:rotateY(180deg)}
.spark{width:100%;height:70px;display:block}
.weeklist{display:flex;flex-direction:column;gap:8px}
.weekrow{display:flex;align-items:center;gap:12px;padding:14px 16px;background:#0f0f13;border:1px solid rgba(255,255,255,.06);border-radius:12px;text-decoration:none;transition:all .2s}
.weekrow:hover{border-color:rgba(56,189,248,.3);background:#16161d}
.weekrow .wk{font-size:15px;font-weight:700;color:#f1f5f9;width:90px}
.weekrow .wr{font-size:12px;color:#64748b;width:80px}
.weekrow .wf{flex:1;font-size:12.5px;color:#94a3b8}
.weekrow .wc{font-size:12px;color:#38bdf8}
.foot{text-align:center;font-size:11px;color:#475569;margin-top:26px;line-height:1.8}
/* 누적 단어·표현 페이지 전용 / cumulative vocab page only */
.wkgroup{margin-bottom:18px}.wkhd{font-size:13px;color:#7dd3fc;font-weight:700;margin:6px 0 8px;border-bottom:1px solid rgba(255,255,255,.06);padding-bottom:6px}
.bgroup{margin-bottom:20px}.bhd{font-size:13px;color:#fbbf24;font-weight:700;margin:6px 0 10px}
.rep{font-size:9px;color:#0f0f13;background:#fbbf24;border-radius:6px;padding:1px 5px;margin-left:6px;vertical-align:middle;font-weight:700}
.src{font-size:9px;border-radius:5px;padding:1px 5px;margin-left:6px;vertical-align:middle;font-weight:700}
.src-t{background:#fb923c;color:#0f0f13}.src-a{background:#38bdf8;color:#0f0f13}
.vlink{display:block;text-align:center;background:linear-gradient(135deg,#1e293b,#16213e);border:1px solid rgba(56,189,248,.25);border-radius:12px;padding:14px;color:#7dd3fc;text-decoration:none;font-size:14px;font-weight:600;margin-bottom:20px}
.vlink:hover{border-color:rgba(56,189,248,.5)}
"""

def render_bars(cum_ls):
    gfreq = Counter(l["grammar_norm"] for l in cum_ls).most_common()
    gmax = max((v for _, v in gfreq), default=1)
    rows = ""
    for i, (k, v) in enumerate(gfreq):
        pct = int(v / gmax * 100); hot = "hot" if i == 0 else ""
        rows += (f'<div class="bar-row"><div class="bar-label">{esc(k)}</div>'
                 f'<div class="bar-track"><div class="bar-fill {hot}" style="width:{pct}%"></div></div>'
                 f'<div class="bar-val">{v}회</div></div>')
    return rows

def render_spark(cum_ls):
    scores = [l["score"] for l in cum_ls if l["score"] is not None]
    if not scores: return ""
    n = len(scores); pts = []
    for i, s in enumerate(scores):
        x = 8 + i * (684 / max(n - 1, 1)); y = 62 - (s - 6.5) / 2.0 * 48
        pts.append(f"{x:.1f},{y:.1f}")
    dots = "".join(f'<circle cx="{p.split(",")[0]}" cy="{p.split(",")[1]}" r="2.5" fill="#38bdf8"/>' for p in pts)
    return (f'<svg viewBox="0 0 700 70" class="spark" preserveAspectRatio="none">'
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="#38bdf8" stroke-width="2"/>{dots}</svg>')

def load_carrot():
    """docs/carrot/*.json(강사 공식 피드백) → {date: [{'original','better'}]}."""
    out = {}
    for f in sorted(glob.glob(os.path.join(DOCS, "carrot", "*.json"))):
        try:
            j = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for it in (j.get("data") or {}).get("list") or []:
            d = (it.get("createDate") or "").strip()
            if not d:
                continue
            ps = []
            for s in it.get("subList") or []:
                o = (s.get("original") or "").strip()
                b = (s.get("better") or "").strip()
                if o or b:
                    ps.append({"original": o, "better": b})
            if ps:
                out.setdefault(d, []).extend(ps)
    return out

def carrot_for_week(carrot_map, iso):
    """그 ISO 주차에 속하는 (날짜, 강사교정쌍들) 리스트 (최신순)."""
    res = []
    for d, ps in (carrot_map or {}).items():
        try:
            y, m, dd = map(int, d.split("-"))
            wi = datetime.date(y, m, dd).isocalendar()
        except Exception:
            continue
        if (wi[0], wi[1]) == iso:
            res.append((d, ps))
    return sorted(res, reverse=True)

def render_carrot_card(iso, carrot_map, ai_pair_count):
    """🎓 강사 vs AI 카드. 그 주 강사 교정이 있을 때만 렌더.
    <div id="carrot_compare"> 는 금요일 루틴 Claude가 비교 통찰로 교체(없어도 동작)."""
    wk = carrot_for_week(carrot_map, iso)
    if not wk:
        return ""
    n = sum(len(ps) for _, ps in wk)
    rows = ""
    for d, ps in wk:
        items = "".join(
            f'<div class="pair"><div class="said">❌ {esc(p["original"])}</div>'
            f'<div class="nat">✅ {esc(p["better"])}</div></div>' for p in ps)
        rows += (f'<div class="lesson"><div class="d">{esc(d[5:])} '
                 f'<span style="color:#64748b">· 강사 교정 {len(ps)}개</span></div>{items}</div>')
    default = (f"이번 주 <b>강사 교정 {n}개</b> · <b>AI 교정 {ai_pair_count}개</b>를 함께 보세요. "
               f"강사가 직접 짚은 교정과 AI가 잡은 약점이 겹치는 부분이 진짜 우선순위입니다.")
    return (f'<div class="card"><h2>🎓 강사 vs AI <span class="sub">강사 직접 작성 · 이번 주 {n}개</span></h2>'
            f'<div class="syn" id="carrot_compare">{default}</div>'
            f'<div style="margin-top:12px">{rows}</div>'
            f'<div class="muted" style="margin-top:8px">전체 강사 피드백 → '
            f'<a href="carrot.html" style="color:#fb923c">🎓 강사 공식 피드백</a></div></div>')

def render_week(iso, week_ls, cum_ls, prev_iso, next_iso, is_current, carrot_map=None):
    week_ls = sorted(week_ls, key=lambda l: l["date"])
    deck = dedup_vocab(cum_ls)
    wk_vocab = [v for l in week_ls for v in l["vocab"]]
    wk_pairs = [p for l in week_ls for p in l["pairs"]]
    avg = avg_score(cum_ls)

    lessons_html = "".join(
        f'<div class="lesson"><div class="d">{l["date"][5:]} · {esc(l["grammar_norm"])}</div>'
        f'<div class="t">{esc(l["topic"][:70])}</div></div>' for l in week_ls)
    pairs_html = "".join(
        f'<div class="pair"><div class="said">❌ {esc(p["said"])}</div>'
        f'<div class="nat">✅ {esc(p["natural"])}</div></div>' for p in wk_pairs) or '<div class="muted">이번 주 교정 표현 없음</div>'
    wkvocab_html = "".join(
        f'<div class="vcard" onclick="this.classList.toggle(\'flipped\')"><div class="vinner">'
        f'<div class="vfront"><span class="vword">{esc(v["word"])}</span><span class="vpos">{esc(v["pos"])}</span></div>'
        f'<div class="vback">{esc(v["meaning"])}</div></div></div>' for v in wk_vocab) or '<div class="muted">이번 주 신규 어휘 없음</div>'

    cur_badge = ' · <span style="color:#fbbf24">진행중</span>' if is_current else ""
    nav_prev = f'<a href="{week_file(prev_iso)}">← {week_label(prev_iso)}</a>' if prev_iso else "<span></span>"
    nav_next = f'<a href="{week_file(next_iso)}">{week_label(next_iso)} →</a>' if next_iso else "<span></span>"
    syn = rule_synthesis(week_ls, cum_ls)

    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>📊 주간 복습 {week_label(iso)}</title><style>{CSS}</style></head><body>
<div class="header"><h1>📊 주간 복습 · {week_label(iso)}</h1>
<div class="range">{week_range(iso)}{cur_badge}</div></div>
<div class="nav">{nav_prev}<a href="review-index.html">📚 전체 목록</a>{nav_next}</div>
<div class="container">

  <div class="stats">
    <div class="stat"><div class="n">{len(week_ls)}</div><div class="l">이번 주 수업</div></div>
    <div class="stat"><div class="n">{len(cum_ls)}</div><div class="l">누적 수업</div></div>
    <div class="stat"><div class="n">{avg:.1f}</div><div class="l">누적 평균</div></div>
    <div class="stat"><div class="n">{len(deck)}</div><div class="l">누적 어휘</div></div>
  </div>

  <div class="card"><h2>🧭 이번 주 종합 <span class="sub">Claude 작성 · $0</span></h2>
    <div class="syn" id="synthesis">{syn}</div></div>

  <div class="card"><h2>📅 이번 주 수업 <span class="sub">{len(week_ls)}회</span></h2>
    {lessons_html or '<div class="muted">이번 주 분석 가능한 수업 없음</div>'}</div>

  <div class="card"><h2>💬 이번 주 교정 표현 <span class="sub">{len(wk_pairs)}개</span></h2>
    {pairs_html}</div>
  {render_carrot_card(iso, carrot_map, len(wk_pairs))}

  <div class="card"><h2>📗 이번 주 어휘 <span class="sub">클릭하면 뜻</span></h2>
    <div class="deck">{wkvocab_html}</div></div>

  <div class="card"><h2>📈 누적 약점 문법 <span class="sub">컷오프~{week_label(iso)}</span></h2>
    {render_bars(cum_ls)}</div>

  <div class="card"><h2>📉 누적 유창성 추이 <span class="sub">평균 {avg:.1f}/10</span></h2>
    {render_spark(cum_ls)}
    <div class="muted" style="margin-top:8px">점수보다 <b style="color:#94a3b8">위 약점 2~3개</b>를 고치는 게 천장을 깨는 길.</div></div>

  <div class="foot">데이터: docs/ 일일 피드백 {CUTOFF} 이후 · 깨진 대용량 파일 자동 제외<br>
  생성: scripts/build_weekly_review.py · Gemini 쿼터 0 · Claude $0</div>
</div>
</body></html>"""

def render_vocab(all_ls, carrot_map=None):
    """누적 단어 & 주요 표현 정리 페이지 (자기완결형, 규칙기반 = Layer 1).
    주요 표현 = AI 일일 교정 + 강사 공식 교정(docs/carrot)을 출처 표시해 병합.
    <div id="curation"> 은 금요일 루틴의 Claude가 더 나은 통찰로 교체 가능(Layer 2, 없어도 동작)."""
    today_ord = iso_ordinal(datetime.date.today().isocalendar()[:2])

    # 💬 주요 표현: AI 교정 + 강사 교정을 주차별 최신순 / merge AI + tutor corrections by week
    weeks = OrderedDict()
    for l in all_ls:
        weeks.setdefault(l["iso"], []).extend(
            {"said": p["said"], "natural": p["natural"], "src": "AI"} for p in l["pairs"])
    ai_pairs = sum(len(v) for v in weeks.values())
    carrot_pairs = 0
    for d, ps in (carrot_map or {}).items():
        if d < CUTOFF:
            continue
        try:
            y, m, dd = map(int, d.split("-"))
            iso = datetime.date(y, m, dd).isocalendar()[:2]
        except Exception:
            continue
        for p in ps:
            weeks.setdefault(iso, []).append(
                {"said": p["original"], "natural": p["better"], "src": "강사"})
            carrot_pairs += 1
    total_pairs = ai_pairs + carrot_pairs

    def _srcbadge(src):
        return ('<span class="src src-t">강사</span>' if src == "강사"
                else '<span class="src src-a">AI</span>')
    expr_html = ""
    for iso in sorted(weeks.keys(), reverse=True):
        prs = sorted(weeks[iso], key=lambda p: p.get("src") != "강사")  # 강사 먼저
        if not prs: continue
        rows = "".join(
            f'<div class="pair"><div class="said">❌ {esc(p["said"])}{_srcbadge(p.get("src"))}</div>'
            f'<div class="nat">✅ {esc(p["natural"])}</div></div>' for p in prs)
        expr_html += (f'<div class="wkgroup"><div class="wkhd">{week_label(iso)} '
                      f'<span class="muted">· {week_range(iso)} · {len(prs)}개</span></div>{rows}</div>')

    # 📗 누적 단어: 최근성 버킷 + 2회↑ 강조 / vocab by recency bucket
    vi = vocab_index(all_ls)
    buckets = {0: [], 1: [], 2: []}
    for v in vi:
        d = today_ord - iso_ordinal(v["last_iso"])
        buckets[0 if d <= 0 else (1 if d <= 3 else 2)].append(v)
    repeat_n = sum(1 for v in vi if v["count"] >= 2)

    def vcard(v):
        badge = '<span class="rep">2회↑</span>' if v["count"] >= 2 else ""
        return ('<div class="vcard" onclick="this.classList.toggle(\'flipped\')"><div class="vinner">'
                f'<div class="vfront"><span class="vword">{esc(v["word"])}{badge}</span>'
                f'<span class="vpos">{esc(v["pos"])}</span></div>'
                f'<div class="vback">{esc(v["meaning"])}</div></div></div>')

    vocab_html = ""
    for b in (0, 1, 2):
        items = buckets[b]
        if not items: continue
        cards = "".join(vcard(v) for v in items)
        vocab_html += (f'<div class="bgroup"><div class="bhd">{VBUCKET[b]} '
                       f'<span class="muted">· {len(items)}개</span></div>'
                       f'<div class="deck">{cards}</div></div>')

    repeat_words = [v["word"] for v in vi if v["count"] >= 2][:6]
    rep_phrase = (f"(특히 <b>{', '.join(esc(w) for w in repeat_words)}</b>) "
                  if repeat_words else "")
    carrot_note = f"(AI {ai_pairs} + 강사 {carrot_pairs})" if carrot_pairs else ""
    curation = (
        f"컷오프({CUTOFF}) 이후 누적 <b>단어 {len(vi)}개</b>, "
        f"<b>주요 표현 {total_pairs}개</b>{carrot_note}를 모았습니다. "
        f"이 중 <b>{repeat_n}개</b> 단어는 2회 이상 반복 등장해 {rep_phrase}우선 암기 대상입니다. "
        f"<b>강사 교정(🟠)</b>과 AI 교정을 함께 훑고, "
        f"❌→✅ 교정 표현은 소리 내어 한 번씩 말해 보세요.")

    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>📚 누적 단어 &amp; 주요 표현</title><style>{CSS}</style></head><body>
<div class="header"><h1>📚 누적 단어 &amp; 주요 표현</h1>
<div class="range">{CUTOFF} ~ 누적 정리 · 매주 금요일 갱신</div></div>
<div class="nav"><a href="review-index.html">← 주간 복습 목록</a><a href="index.html">일일 복습 →</a></div>
<div class="container">

  <div class="stats">
    <div class="stat"><div class="n">{len(vi)}</div><div class="l">누적 단어</div></div>
    <div class="stat"><div class="n">{total_pairs}</div><div class="l">주요 표현</div></div>
    <div class="stat"><div class="n">{len(weeks)}</div><div class="l">분석 주차</div></div>
    <div class="stat"><div class="n">{repeat_n}</div><div class="l">2회↑ 단어</div></div>
  </div>

  <div class="card"><h2>🧭 누적 학습 큐레이션 <span class="sub">Claude 작성 · $0</span></h2>
    <div class="syn" id="curation">{curation}</div></div>

  <div class="card"><h2>💬 주요 표현 <span class="sub">❌→✅ · <span class="src src-a">AI</span>{ai_pairs}+<span class="src src-t">강사</span>{carrot_pairs} · 최신순</span></h2>
    {expr_html or '<div class="muted">교정 표현 없음</div>'}</div>

  <div class="card"><h2>📗 누적 단어 <span class="sub">클릭하면 뜻 · 최근순</span></h2>
    {vocab_html or '<div class="muted">단어 없음</div>'}</div>

  <div class="foot">데이터: docs/ 일일 피드백 {CUTOFF} 이후 · 깨진 대용량 파일 자동 제외<br>
  생성: scripts/build_weekly_review.py · Gemini 쿼터 0 · Claude $0</div>
</div>
</body></html>"""

def render_index(weeks, all_ls):
    deck = dedup_vocab(all_ls); avg = avg_score(all_ls)
    gtop = Counter(l["grammar_norm"] for l in all_ls).most_common(1)
    top = gtop[0][0] if gtop else "—"
    rows = ""
    for iso, wls in sorted(weeks.items(), reverse=True):
        focus = ", ".join(sorted({l["grammar_norm"] for l in wls}))[:50]
        rows += (f'<a class="weekrow" href="{week_file(iso)}">'
                 f'<span class="wk">{week_label(iso)}</span>'
                 f'<span class="wr">{week_range(iso)}</span>'
                 f'<span class="wf">{esc(focus)}</span>'
                 f'<span class="wc">{len(wls)}회</span></a>')
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>📚 주간 복습 기록</title><style>{CSS}</style></head><body>
<div class="header"><h1>📚 주간 복습 기록</h1>
<div class="range">{CUTOFF} ~ 누적 {len(all_ls)} LESSONS</div></div>
<div class="nav"><a href="index.html">← 일일 복습 목록</a><a href="review-vocab.html">📚 누적 단어·표현 →</a></div>
<div class="container">
  <div class="stats">
    <div class="stat"><div class="n">{len(weeks)}</div><div class="l">주차</div></div>
    <div class="stat"><div class="n">{len(all_ls)}</div><div class="l">누적 수업</div></div>
    <div class="stat"><div class="n">{avg:.1f}</div><div class="l">평균 유창성</div></div>
    <div class="stat"><div class="n">{len(deck)}</div><div class="l">누적 어휘</div></div>
  </div>
  <a class="vlink" href="review-vocab.html">📚 누적 단어 &amp; 주요 표현 모아보기 →</a>
  <div class="card"><h2>🔧 누적 약점 문법 <span class="sub">최다: {esc(top)}</span></h2>
    {render_bars(all_ls)}</div>
  <div class="card"><h2>🗓 주간 리포트 <span class="sub">최신순</span></h2>
    <div class="weeklist">{rows}</div></div>
  <div class="foot">생성: scripts/build_weekly_review.py · 매주 금요일 자동 갱신 예정 · Claude $0</div>
</div></body></html>"""

# ───────────────────────── main ─────────────────────────
def build():
    allL = load_all()
    weeks = OrderedDict()
    for l in allL:
        weeks.setdefault(l["iso"], []).append(l)
    ordered = sorted(weeks.keys())
    today_iso = datetime.date.today().isocalendar()
    current = (today_iso[0], today_iso[1])
    current_file = None
    carrot_map = load_carrot()   # 🎓 강사 공식 피드백 (docs/carrot/*.json)

    for i, iso in enumerate(ordered):
        week_ls = weeks[iso]
        cum_ls = [l for l in allL if l["iso"] <= iso]   # 그 주말까지 누적
        prev_iso = ordered[i-1] if i > 0 else None
        next_iso = ordered[i+1] if i < len(ordered)-1 else None
        is_current = (iso == current)
        page = render_week(iso, week_ls, cum_ls, prev_iso, next_iso, is_current, carrot_map)
        path = os.path.join(DOCS, week_file(iso))
        open(path, "w", encoding="utf-8").write(page)
        if is_current: current_file = week_file(iso)

    open(os.path.join(DOCS, "review-index.html"), "w", encoding="utf-8").write(render_index(weeks, allL))
    open(os.path.join(DOCS, "review-vocab.html"), "w", encoding="utf-8").write(render_vocab(allL, carrot_map))

    print(f"✅ {len(weeks)} weekly files + review-index.html + review-vocab.html")
    for iso in ordered:
        tag = " (current)" if iso == current else ""
        print(f"   {week_file(iso)}  {len(weeks[iso])} lessons{tag}")
    # 루틴이 현재 주 파일을 식별할 수 있도록 마지막 줄에 출력
    print(f"CURRENT_WEEK_FILE={current_file or (week_file(ordered[-1]) if ordered else '')}")

if __name__ == "__main__":
    build()

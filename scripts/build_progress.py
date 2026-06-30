#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📈 진척 대시보드 + 🎯 능동복습 퀴즈 빌더 / Progress dashboard + active-recall quiz builder.

  - 단일 진실원천 = docs/data/*.json (구조화 데이터). HTML 재스크랩 없음.
  - 순수 표준 라이브러리(외부 의존성 0). 매일 돌려도 비용 0.
  - 산출물: docs/progress.html (탭 2개: 📈 진척 / 🎯 복습 퀴즈)
  - <div class="syn" id="coach"> 안의 코칭 한마디는 금요일 루틴의 Claude가 더 나은 통찰로
    교체한다(라디오 #radio-src·주간 #synthesis 와 동일한 'preserve div' 패턴).
    → 매일 빌드는 차트/퀴즈(기계적)만 갱신하고, 이 div 내용은 기존 파일에서 보존한다.

The single source of truth is docs/data/*.json. Pure stdlib, zero cost to rebuild daily.
Output docs/progress.html has two tabs (Progress / Review Quiz). The #coach insight div is
preserved across daily rebuilds and upgraded by Claude in the Friday routine.
"""
import glob, os, re, json, html, datetime
from collections import Counter, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOCS = os.path.join(ROOT, "docs")
DATA = os.path.join(DOCS, "data")
OUT = os.path.join(DOCS, "progress.html")
CARROT = os.path.join(DOCS, "carrot")
CUTOFF = "2026-05-08"   # 집계 시작일 (build_weekly_review 와 동일 기준)

def esc(s): return html.escape(str(s), quote=True)

# ───────────────────────── 데이터 로드 / load ─────────────────────────
def load_all():
    out = []
    for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        date = os.path.basename(f)[:10]
        if date < CUTOFF:
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

def week_label(iso): return f"{iso[0]}-W{iso[1]:02d}" if iso else "?"

def load_carrot_corrections():
    """강사(Carrot) 교정쌍 original→better 을 퀴즈 풀에 합류 (출처 뱃지 'tutor')."""
    out = []
    for f in sorted(glob.glob(os.path.join(CARROT, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for item in (d.get("data", {}) or {}).get("list", []) or []:
            for sub in item.get("subList", []) or []:
                o = (sub.get("original") or "").strip()
                b = (sub.get("better") or "").strip()
                if o and b and o.lower() != b.lower():
                    out.append({"said": o, "natural": b, "src": "tutor"})
    return out

# ───────────────────────── 집계 / aggregate ─────────────────────────
def aggregate(rows):
    scored = [(r["date"], r["score"]) for r in rows if r.get("score") is not None]
    scores = [s for _, s in scored]
    avg = round(sum(scores) / len(scores), 1) if scores else 0
    weeks = OrderedDict()
    for r in rows:
        wl = week_label(r.get("iso"))
        weeks.setdefault(wl, []).append(r)
    week_avgs = []
    for wl, ws in weeks.items():
        s = [x["score"] for x in ws if x.get("score") is not None]
        week_avgs.append((wl, round(sum(s) / len(s), 1) if s else None, len(ws)))
    weak = Counter(r.get("grammar_norm") or "?" for r in rows).most_common()
    # 누적 어휘 dedup
    vseen, vocab = set(), []
    for r in rows:
        for v in r.get("vocab", []):
            k = (v.get("word") or "").lower()
            if k and k not in vseen:
                vseen.add(k); vocab.append(v)
    return {
        "total": len(rows), "avg": avg, "weeks": len(weeks),
        "vocab_n": len(vocab), "scored": scored, "week_avgs": week_avgs,
        "weak": weak, "vocab": vocab,
    }

def build_quiz_pool(rows, carrot):
    """❌→✅ 인출 카드 풀. 교정쌍(AI) + 강사 교정 + 어휘. 중복 제거."""
    pool, seen = [], set()
    def add(card):
        key = (card.get("said", "") + "→" + card.get("natural", "")).lower()
        if key in seen:
            return
        seen.add(key); pool.append(card)
    for r in rows:
        wl = week_label(r.get("iso"))
        for p in r.get("pairs", []):
            said = (p.get("said") or "").strip()
            nat = (p.get("natural") or "").strip()
            if said and nat and len(nat) < 240:
                add({"type": "correction", "said": said, "natural": nat,
                     "topic": r.get("topic", ""), "week": wl, "src": "ai"})
    for c in carrot:
        add({"type": "correction", "said": c["said"], "natural": c["natural"],
             "topic": "강사 교정", "week": "", "src": "tutor"})
    # 어휘 카드
    vseen = set()
    for r in rows:
        for v in r.get("vocab", []):
            w = (v.get("word") or "").strip()
            m = (v.get("meaning") or "").strip()
            if w and m and w.lower() not in vseen:
                vseen.add(w.lower())
                pool.append({"type": "vocab", "word": w, "meaning": m,
                             "pos": v.get("pos", ""), "src": "ai"})
    return pool

# ───────────────────────── SVG 스파크라인 / sparkline ─────────────────────────
def sparkline(scored):
    """일자별 유창성 점수 추세선 (0~10 스케일)."""
    if len(scored) < 2:
        return '<div class="muted">데이터가 더 모이면 추세선이 그려집니다.</div>'
    vals = [s for _, s in scored]
    W, H, pad = 700, 120, 8
    n = len(vals)
    def x(i): return pad + (W - 2 * pad) * i / (n - 1)
    def y(v): return H - pad - (H - 2 * pad) * (v / 10.0)
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    dots = "".join(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="2.4" fill="#38bdf8"/>'
                   for i, v in enumerate(vals))
    # 평균선
    avg = sum(vals) / n
    ay = y(avg)
    return (f'<svg viewBox="0 0 {W} {H}" class="spark" preserveAspectRatio="none" '
            f'style="width:100%;height:120px">'
            f'<line x1="{pad}" y1="{ay:.1f}" x2="{W-pad}" y2="{ay:.1f}" '
            f'stroke="#475569" stroke-width="1" stroke-dasharray="4 4"/>'
            f'<polyline points="{pts}" fill="none" stroke="#38bdf8" stroke-width="2.2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>{dots}'
            f'<text x="{W-pad}" y="{ay-5:.1f}" fill="#64748b" font-size="11" '
            f'text-anchor="end">평균 {avg:.1f}</text></svg>')

# ───────────────────────── HTML ─────────────────────────
CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Noto Sans KR',-apple-system,sans-serif;background:#0f0f13;color:#e4e4e7;line-height:1.7}
.header{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);padding:42px 24px 26px;text-align:center;border-bottom:1px solid rgba(255,255,255,.06)}
.header h1{font-size:24px;color:#f1f5f9;margin-bottom:8px}
.header .range{font-size:13px;color:#94a3b8;letter-spacing:2px}
.nav{max-width:760px;margin:0 auto;padding:14px 20px 0;display:flex;gap:8px;font-size:13px}
.nav a{color:#64748b;text-decoration:none;padding:6px 10px;border-radius:8px}
.nav a:hover{color:#38bdf8;background:#16161d}
.container{max-width:760px;margin:0 auto;padding:18px 20px 90px}
.card{background:#16161d;border:1px solid rgba(255,255,255,.06);border-radius:16px;padding:22px;margin-bottom:20px}
.card h2{font-size:16px;color:#f1f5f9;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.card h2 .sub{font-size:12px;color:#64748b;font-weight:400;margin-left:auto}
.muted{color:#64748b;font-size:12px}.syn{color:#cbd5e1;font-size:14px}.syn b{color:#f1f5f9}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px}
.stat{background:#16161d;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:16px 8px;text-align:center}
.stat .n{font-size:22px;font-weight:700;color:#38bdf8}.stat .l{font-size:11px;color:#94a3b8;margin-top:4px}
.bar-row{display:flex;align-items:center;gap:10px;margin:8px 0}
.bar-label{width:170px;font-size:12.5px;color:#cbd5e1;text-align:right;flex-shrink:0}
.bar-track{flex:1;background:#0f0f13;border-radius:6px;height:20px;overflow:hidden}
.bar-fill{height:100%;background:linear-gradient(90deg,#3b82f6,#818cf8);border-radius:6px}
.bar-fill.hot{background:linear-gradient(90deg,#f43f5e,#fb7185)}
.bar-val{width:34px;font-size:12px;color:#94a3b8;flex-shrink:0}
.wk{display:flex;align-items:center;gap:10px;margin:7px 0;font-size:12.5px}
.wk .wl{width:90px;color:#7dd3fc;font-weight:600}
.wk .wt{flex:1;background:#0f0f13;border-radius:6px;height:16px;overflow:hidden}
.wk .wf{height:100%;background:linear-gradient(90deg,#22d3ee,#818cf8)}
.wk .wv{width:60px;color:#94a3b8;text-align:right}
/* 탭 */
.tabs{max-width:760px;margin:16px auto 0;padding:0 20px;display:flex;gap:8px}
.tab{flex:1;text-align:center;padding:11px;border-radius:12px 12px 0 0;background:#16161d;color:#94a3b8;
  font-size:14px;font-weight:600;cursor:pointer;border:1px solid rgba(255,255,255,.06);border-bottom:none}
.tab.on{background:#0f3460;color:#f1f5f9}
.pane{display:none}.pane.on{display:block}
/* 퀴즈 카드 */
.quizwrap{text-align:center}
.qmeta{display:flex;justify-content:space-between;align-items:center;font-size:12px;color:#64748b;margin-bottom:12px}
.qcard{position:relative;min-height:210px;background:#16161d;border:1px solid rgba(255,255,255,.08);
  border-radius:18px;padding:30px 22px;display:flex;flex-direction:column;justify-content:center;gap:14px}
.qtag{position:absolute;top:12px;left:14px;font-size:11px;color:#64748b}
.qsrc{position:absolute;top:12px;right:14px;font-size:11px;padding:2px 8px;border-radius:20px}
.qsrc.ai{background:rgba(129,140,248,.15);color:#a5b4fc}
.qsrc.tutor{background:rgba(251,146,60,.15);color:#fdba74}
.qprompt{font-size:13px;color:#94a3b8}
.qfront{font-size:18px;color:#fca5a5;font-weight:600}
.qfront.vocab{color:#fcd34d}
.qback{font-size:18px;color:#86efac;font-weight:600;border-top:1px dashed rgba(255,255,255,.12);padding-top:14px}
.qhint{font-size:13px;color:#64748b;font-style:italic}
.qbtns{display:flex;gap:10px;margin-top:18px;justify-content:center;flex-wrap:wrap}
.qbtn{padding:12px 20px;border-radius:12px;border:1px solid rgba(255,255,255,.1);background:#1e293b;
  color:#e2e8f0;font-size:14px;font-weight:600;cursor:pointer;transition:all .15s}
.qbtn:hover{transform:translateY(-1px)}
.qbtn.primary{background:linear-gradient(135deg,#38bdf8,#818cf8);color:#fff;border:none}
.qbtn.know{background:#14532d;color:#86efac}.qbtn.again{background:#7c2d12;color:#fdba74}
.qbar{height:6px;background:#0f0f13;border-radius:6px;overflow:hidden;margin-bottom:16px}
.qbar i{display:block;height:100%;background:linear-gradient(90deg,#22d3ee,#818cf8);transition:width .3s}
.foot{text-align:center;color:#475569;font-size:11px;margin-top:24px}
"""

def render(rows, agg, pool, coach_html, week_now):
    s = agg
    # 통계 4칸
    stats = (
        f'<div class="stat"><div class="n">{s["total"]}</div><div class="l">누적 수업</div></div>'
        f'<div class="stat"><div class="n">{s["avg"]}</div><div class="l">평균 유창성/10</div></div>'
        f'<div class="stat"><div class="n">{s["weeks"]}</div><div class="l">추적 주차</div></div>'
        f'<div class="stat"><div class="n">{s["vocab_n"]}</div><div class="l">누적 어휘</div></div>'
    )
    # 약점 Top-N 바
    weak = s["weak"][:6]
    wmax = max((c for _, c in weak), default=1)
    weak_rows = "".join(
        f'<div class="bar-row"><div class="bar-label">{esc(k)}</div>'
        f'<div class="bar-track"><div class="bar-fill{" hot" if i == 0 else ""}" '
        f'style="width:{c/wmax*100:.0f}%"></div></div><div class="bar-val">{c}회</div></div>'
        for i, (k, c) in enumerate(weak)
    ) or '<div class="muted">데이터가 모이면 약점 랭킹이 나타납니다.</div>'
    # 주차별 평균 막대
    wamax = 10
    wk_rows = "".join(
        f'<div class="wk"><div class="wl">{esc(wl)}</div>'
        f'<div class="wt"><div class="wf" style="width:{(av or 0)/wamax*100:.0f}%"></div></div>'
        f'<div class="wv">{("%.1f" % av) if av is not None else "—"} · {n}회</div></div>'
        for wl, av, n in s["week_avgs"]
    )
    quiz_json = json.dumps(pool, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="theme-color" content="#0f0f13">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<title>📈 진척 & 복습 퀴즈</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<div class="header">
  <h1>📈 나의 영어 진척 & 🎯 복습 퀴즈</h1>
  <div class="range">{esc(week_now)} 기준 · 누적 {s["total"]}회 수업</div>
</div>
<div class="nav">
  <a href="index.html">← 홈</a>
  <a href="review-index.html">주간 복습</a>
  <a href="carrot.html">강사 피드백</a>
  <a href="radio.html">라디오</a>
</div>
<div class="tabs">
  <div class="tab on" data-pane="prog" onclick="tab('prog')">📈 진척</div>
  <div class="tab" data-pane="quiz" onclick="tab('quiz')">🎯 복습 퀴즈</div>
</div>
<div class="container">

  <div class="pane on" id="prog">
    <div class="stats">{stats}</div>
    <div class="card">
      <h2>🎯 이번 주 코칭 <span class="sub">금요일 Claude 갱신</span></h2>
      <div class="syn" id="coach">{coach_html}</div>
    </div>
    <div class="card">
      <h2>📈 유창성 점수 추세 <span class="sub">일자별 · 0~10</span></h2>
      {sparkline(s["scored"])}
    </div>
    <div class="card">
      <h2>🔁 가장 끈질긴 약점 <span class="sub">반복 횟수</span></h2>
      {weak_rows}
      <div class="muted" style="margin-top:10px">붉은 막대 = 1순위 — 퀴즈 탭에서 집중 인출 연습하세요.</div>
    </div>
    <div class="card">
      <h2>🗓 주차별 평균 유창성 <span class="sub">주 · 수업수</span></h2>
      {wk_rows}
    </div>
  </div>

  <div class="pane" id="quiz">
    <div class="card quizwrap">
      <div class="qbar"><i id="qprog" style="width:0%"></i></div>
      <div class="qmeta"><span id="qcount">0 / 0</span>
        <select id="qmode" onchange="rebuild()" style="background:#1e293b;color:#cbd5e1;border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:4px 8px;font-size:12px">
          <option value="all">전체</option>
          <option value="correction">교정만 (❌→✅)</option>
          <option value="vocab">어휘만</option>
          <option value="again">또 볼래요만</option>
        </select></div>
      <div class="qcard" id="qcard"><div class="qprompt">로딩 중…</div></div>
      <div class="qbtns" id="qbtns"></div>
      <div class="muted" style="margin-top:14px">스페이스/탭 = 뒤집기 · ←→ = 이동 · 표시는 이 기기에 저장됩니다(localStorage).</div>
    </div>
  </div>

  <div class="foot">생성: scripts/build_progress.py · 데이터: docs/data/*.json · 비용 0 · 매일 자동 갱신 + 금요일 코칭</div>
</div>

<script id="quiz-data" type="application/json">{quiz_json}</script>
<script>
function tab(p){{document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('on',t.dataset.pane===p));
  document.querySelectorAll('.pane').forEach(e=>e.classList.toggle('on',e.id===p));
  if(p==='quiz')ensureQuiz();}}

// ───── 능동복습 퀴즈 (active recall) ─────
const POOL=JSON.parse(document.getElementById('quiz-data').textContent||'[]');
const LS='efb_quiz_v1';
function loadState(){{try{{return JSON.parse(localStorage.getItem(LS)||'{{}}')}}catch(e){{return {{}}}}}}
function saveState(s){{try{{localStorage.setItem(LS,JSON.stringify(s))}}catch(e){{}}}}
function cardKey(c){{return c.type==='vocab'?('v:'+c.word):('c:'+c.said).slice(0,80);}}
let DECK=[],pos=0,flipped=false,started=false;
function shuffle(a){{for(let i=a.length-1;i>0;i--){{const j=Math.floor(((i+1)*((Date.now()+i)%9973))/9973)%(i+1);[a[i],a[j]]=[a[j],a[i]];}}return a;}}
function rebuild(){{
  const mode=document.getElementById('qmode').value, st=loadState();
  let d=POOL.slice();
  if(mode==='correction')d=d.filter(c=>c.type==='correction');
  else if(mode==='vocab')d=d.filter(c=>c.type==='vocab');
  else if(mode==='again')d=d.filter(c=>st[cardKey(c)]==='again');
  // '또 볼래요'를 앞쪽으로 가중
  shuffle(d);
  d.sort((a,b)=>(st[cardKey(b)]==='again'?1:0)-(st[cardKey(a)]==='again'?1:0));
  DECK=d;pos=0;flipped=false;render();
}}
function ensureQuiz(){{if(!started){{started=true;rebuild();}}}}
function render(){{
  const card=document.getElementById('qcard'),btns=document.getElementById('qbtns');
  document.getElementById('qcount').textContent=(DECK.length?(pos+1):0)+' / '+DECK.length;
  document.getElementById('qprog').style.width=(DECK.length?((pos)/DECK.length*100):0)+'%';
  if(!DECK.length){{card.innerHTML='<div class="qprompt">이 모드에 카드가 없습니다. 다른 모드를 골라보세요.</div>';btns.innerHTML='';return;}}
  const c=DECK[pos],st=loadState(),mark=st[cardKey(c)];
  const srcBadge='<span class="qsrc '+(c.src||'ai')+'">'+((c.src==='tutor')?'강사':'AI')+'</span>';
  if(c.type==='vocab'){{
    card.innerHTML='<span class="qtag">어휘'+(c.pos?(' · '+c.pos):'')+'</span>'+srcBadge+
      '<div class="qprompt">이 단어의 뜻은?</div><div class="qfront vocab">'+esc(c.word)+'</div>'+
      (flipped?('<div class="qback">'+esc(c.meaning)+'</div>'):'<div class="qhint">탭하면 뜻이 보여요</div>');
  }}else{{
    card.innerHTML='<span class="qtag">교정'+(c.week?(' · '+c.week):'')+'</span>'+srcBadge+
      '<div class="qprompt">더 자연스럽게 고쳐 말해보세요</div><div class="qfront">❌ '+esc(c.said)+'</div>'+
      (flipped?('<div class="qback">✅ '+esc(c.natural)+'</div>'):'<div class="qhint">탭하면 모범답안이 보여요</div>');
  }}
  card.onclick=()=>{{flipped=!flipped;render();}};
  btns.innerHTML = !flipped
    ? '<button class="qbtn primary" onclick="flip(event)">뒤집기 👀</button>'
    : '<button class="qbtn again" onclick="grade(event,\\'again\\')">🔁 또 볼래요</button>'+
      '<button class="qbtn know" onclick="grade(event,\\'know\\')">✅ 알아요</button>'+
      '<button class="qbtn" onclick="nav(event,1)">다음 →</button>';
}}
function esc(s){{return String(s).replace(/[&<>]/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[m]));}}
function flip(e){{if(e)e.stopPropagation();flipped=!flipped;render();}}
function grade(e,g){{if(e)e.stopPropagation();const st=loadState();st[cardKey(DECK[pos])]=g;saveState(st);nav(null,1);}}
function nav(e,dir){{if(e)e.stopPropagation();if(!DECK.length)return;pos=(pos+dir+DECK.length)%DECK.length;flipped=false;render();}}
document.addEventListener('keydown',ev=>{{
  if(!document.getElementById('quiz').classList.contains('on'))return;
  if(ev.code==='Space'||ev.code==='Tab'){{ev.preventDefault();flip();}}
  else if(ev.code==='ArrowRight')nav(null,1);
  else if(ev.code==='ArrowLeft')nav(null,-1);
}});
</script>
</body></html>"""

# ───────────────────────── coach 보존 / preserve ─────────────────────────
DEFAULT_COACH = ('이번 주 데이터를 모아 가장 끈질긴 약점과 다음 주 처방을 여기에 적어 드립니다. '
                 '(금요일 루틴에서 Claude가 실제 교정 내용을 읽고 교체합니다.)')

def existing_coach():
    if not os.path.exists(OUT):
        return None
    try:
        t = open(OUT, encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(r'<div class="syn" id="coach">(.*?)</div>', t, re.S)
    if m:
        inner = m.group(1).strip()
        if inner and "여기에 적어 드립니다" not in inner:
            return inner
    return None

def main():
    rows = load_all()
    agg = aggregate(rows)
    pool = build_quiz_pool(rows, load_carrot_corrections())
    coach = existing_coach() or DEFAULT_COACH
    week_now = week_label(rows[-1]["iso"]) if rows else "—"
    html_out = render(rows, agg, pool, coach, week_now)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"wrote {OUT}  lessons={agg['total']} weeks={agg['weeks']} "
          f"quiz_cards={len(pool)} weakest={agg['weak'][0] if agg['weak'] else '—'}")

if __name__ == "__main__":
    main()

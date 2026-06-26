#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎙️ 영어 주간 라디오 생성기 / Weekly English radio page.

누적 피드백(AI 일일 + 강사 공식 + 약점·어휘)에서 '라디오 담화 대본'을 만들고,
docs/radio.html 로 렌더한다. 페이지는 브라우저 Web Speech API(speechSynthesis)로
대본을 두 진행자(민지=MC, 알렉스=코치) 음성으로 읽어준다 — 서버·오디오파일·비용 0.
대화/강의/라디오 인터뷰 3가지 'AI와 대화' 모드 프롬프트(클릭→복사→Gemini)도 포함.

설계:
  - 대본은 규칙기반 폴백으로 항상 채워진다(파일이 깨지지 않음).
  - <pre id="radio-src"> 안의 'speaker|lang|text' 라인이 단일 진실원천(SSOT).
    금요일 루틴의 Claude가 이 내용을 더 자연스러운 담화로 교체 가능(없어도 동작).

CLI:  python3 scripts/build_radio.py
"""
import os, sys, html, datetime
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_weekly_review as W  # 데이터 파싱 재사용 (load_all/load_carrot/avg_score/week_*)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")


def esc(s):
    return html.escape(str(s or ""), quote=True)


def _clean1(s):
    """TTS 한 줄용: 개행 제거 + 구분자 | 치환."""
    return " ".join(str(s or "").split()).replace("|", "/").strip()


def carrot_pairs_for_dates(carrot_map, dates):
    out = []
    for d in sorted(dates, reverse=True):
        for p in carrot_map.get(d, []):
            if p.get("original") or p.get("better"):
                out.append(p)
    return out


def build_script(wk_iso, wk, lessons, carrot_map):
    """규칙기반 라디오 대본 → [(speaker, lang, text), ...]."""
    ai_pairs = [p for l in wk for p in l["pairs"]]
    vocab = [v for l in wk for v in l["vocab"]]
    wk_dates = {l["date"] for l in wk}
    cpairs = carrot_pairs_for_dates(carrot_map, wk_dates)
    weak = Counter(l["grammar_norm"] for l in lessons).most_common()
    top = weak[0][0] if weak else "문법"
    topn = weak[0][1] if weak else 0
    avg = W.avg_score(lessons)

    # 규칙기반 폴백: 전부 영어 + 한 주 교정·어휘를 통째로 망라(길게).
    # (금요일 루틴의 Claude가 #radio-src 를 더 풍성한 담화로 교체.)
    L = []
    add = lambda s, lang, t: L.append((s, lang, _clean1(t)))
    wl = W.week_label(wk_iso)
    add("민지", "en", "Hello and welcome to your Weekly English Radio! I'm Minji, your host.")
    add("알렉스", "en", f"And I'm Alex, your coach. This is {wl}, with {len(wk)} lessons this week. Let's review the whole week together.")
    add("민지", "en", f"The pattern to watch is {top}. It has come up {topn} times so far, so let's keep an eye on it.")
    add("알렉스", "en", "First up, the Correction Clinic. Here are sentences you said, made to sound natural.")
    for p in ai_pairs[:18]:
        if p.get("said") and p.get("natural"):
            add("알렉스", "en", f"You said: {p['said']}")
            add("민지", "en", f"More naturally: {p['natural']}")
    if cpairs:
        add("알렉스", "en", "Your tutor also marked several corrections this week. Listen closely.")
        for cp in cpairs[:18]:
            if cp.get("original") and cp.get("better"):
                add("민지", "en", f"Instead of: {cp['original']}")
                add("알렉스", "en", f"Say: {cp['better']}")
    if vocab:
        add("민지", "en", "Now the Vocabulary Builder. Here are this week's useful words to practice.")
        for v in vocab[:10]:
            if v.get("word"):
                add("알렉스", "en", f"Word of the day: {v['word']}. Try using it in a sentence this week.")
    add("민지", "en", f"Quick recap. Your fluency average this week was {avg:.1f} out of ten. Nicely done.")
    add("알렉스", "en", f"Your mission for next week: slow down and check {top} every time you speak.")
    add("민지", "en", "That's all for this week's English Radio. Have a wonderful week, and see you next Friday!")
    add("알렉스", "en", "Bye for now, and keep up the great work!")
    return L


def build_chat_prompts(wk_iso, wk, lessons, carrot_map):
    """C: 대화/강의/라디오 인터뷰 3모드 프롬프트(클릭→복사→Gemini)."""
    ai_pairs = [p for l in wk for p in l["pairs"]][:6]
    vocab = [v for l in wk for v in l["vocab"]][:6]
    wk_dates = {l["date"] for l in wk}
    cpairs = carrot_pairs_for_dates(carrot_map, wk_dates)[:6]
    weak = Counter(l["grammar_norm"] for l in lessons).most_common(3)

    lines = [f"[이번 주: {W.week_label(wk_iso)} · {len(wk)}회 수업]"]
    if weak:
        lines.append("누적 약점 Top: " + ", ".join(f"{k}({v}회)" for k, v in weak))
    if ai_pairs:
        lines.append("AI 교정(❌→✅):")
        lines += [f"  - {p['said']} → {p['natural']}" for p in ai_pairs if p.get('said')]
    if cpairs:
        lines.append("강사 교정(❌→✅):")
        lines += [f"  - {p.get('original','')} → {p.get('better','')}" for p in cpairs]
    if vocab:
        lines.append("핵심 어휘: " + ", ".join(f"{v.get('word','')}({v.get('meaning','')})" for v in vocab))
    data = "\n".join(lines)

    base = f"아래는 이번 주 내 전화영어 학습 요약이야.\n\n{data}\n\n"
    return {
        "chat": base + ("위 약점·교정을 주제로 나와 영어로 대화하면서 복습시켜줘. 먼저 약점 1개와 관련된 상황을 영어로 질문하고, "
                        "내 대답이 자연스러운지 교정해줘. 한국어 설명은 필요할 때만 짧게."),
        "lecture": base + ("위 내용을 강의식으로 차근차근 설명해줘. 각 약점이 왜 틀렸는지 규칙을 짚고, 쉬운 예문 2~3개씩 더 들어주고, "
                           "마지막에 1분 요약과 연습문제 3개를 줘."),
        "radio": base + ("너는 라디오 진행자, 나는 오늘의 게스트야. 내 이번 주 영어 학습 여정을 주제로 인터뷰하듯 대화해줘. "
                         "가볍고 격려하는 톤으로, 중간중간 위 교정 표현을 자연스럽게 연습시켜줘. 영어 위주, 한국어는 가끔."),
    }


CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Noto Sans KR',-apple-system,sans-serif;background:#0f0f13;color:#e4e4e7;line-height:1.7}
.header{background:linear-gradient(135deg,#241a3a,#3a2410,#0f3460);padding:42px 24px 30px;text-align:center;border-bottom:1px solid rgba(255,255,255,.06)}
.header h1{font-size:24px;color:#f5f0ff;margin-bottom:8px}
.header .range{font-size:13px;color:#c4b5fd;letter-spacing:1px}
.nav{max-width:760px;margin:0 auto;padding:14px 20px 0;display:flex;justify-content:space-between;font-size:13px}
.nav a{color:#64748b;text-decoration:none;padding:6px 10px;border-radius:8px}.nav a:hover{color:#a78bfa;background:#16161d}
.container{max-width:760px;margin:0 auto;padding:18px 20px 80px}
.card{background:#16161d;border:1px solid rgba(255,255,255,.06);border-radius:16px;padding:20px;margin-bottom:18px}
.card h2{font-size:16px;color:#f1f5f9;margin-bottom:12px}
.player{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:14px}
.pbtn{border:none;border-radius:10px;padding:12px 18px;font-size:14px;font-weight:700;cursor:pointer;font-family:inherit;color:#0f0f13;background:linear-gradient(135deg,#a78bfa,#818cf8)}
.pbtn.alt{background:#1e293b;color:#cbd5e1}
.pbtn:active{transform:translateY(1px)}
.speed{display:flex;align-items:center;gap:6px;font-size:12px;color:#94a3b8;margin-left:auto}
.speed input{accent-color:#a78bfa}
.stage{display:flex;flex-direction:column;gap:10px;margin-top:6px}
.bubble{max-width:88%;padding:11px 14px;border-radius:14px;font-size:14px;border:1px solid transparent;transition:all .2s}
.bubble .who{display:block;font-size:11px;font-weight:700;margin-bottom:3px;opacity:.8}
.bubble.mc{align-self:flex-start;background:#1e1b2e;border-color:rgba(167,139,250,.25)}.bubble.mc .who{color:#a78bfa}
.bubble.coach{align-self:flex-end;background:#1a2433;border-color:rgba(56,189,248,.22)}.bubble.coach .who{color:#38bdf8}
.bubble.on{border-color:#fbbf24;box-shadow:0 0 0 1px #fbbf24}
.modes{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.mode{display:flex;flex-direction:column;gap:4px;align-items:center;padding:16px 10px;background:#0f0f13;border:1px solid rgba(255,255,255,.08);border-radius:12px;color:#cbd5e1;cursor:pointer;font-size:13px;text-align:center}
.mode:hover{border-color:rgba(167,139,250,.4);color:#a78bfa}.mode .ico{font-size:22px}.mode .sub{font-size:11px;color:#64748b}
.muted{color:#64748b;font-size:12px}
.toast{position:fixed;bottom:28px;left:50%;transform:translateX(-50%) translateY(80px);background:#1e293b;color:#a78bfa;padding:13px 26px;border-radius:12px;font-size:14px;border:1px solid rgba(167,139,250,.25);opacity:0;transition:all .4s;z-index:99}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.epweek{font-size:13px;color:#a78bfa;font-weight:700;margin-bottom:6px}
audio{width:100%;margin-top:4px}
.archive{display:flex;flex-direction:column;gap:6px;margin-top:10px}
.archive a{font-size:12.5px;color:#94a3b8;text-decoration:none;padding:8px 12px;background:#0f0f13;border:1px solid rgba(255,255,255,.06);border-radius:8px}
.archive a:hover{color:#a78bfa;border-color:rgba(167,139,250,.3)}
.foot{text-align:center;font-size:11px;color:#475569;margin-top:26px;line-height:1.8}
"""


def render(wk_iso, script_lines, prompts):
    src = "\n".join(f"{s}|{lang}|{t}" for s, lang, t in script_lines)
    import json as _json
    P = {k: _json.dumps(v, ensure_ascii=False) for k, v in prompts.items()}
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🎙️ 영어 주간 라디오</title><style>{CSS}</style></head><body>
<div class="header"><h1>🎙️ 영어 주간 라디오</h1>
<div class="range">{W.week_label(wk_iso)} · {W.week_range(wk_iso)} · 매주 자동 갱신</div></div>
<div class="nav"><a href="index.html">← 일일 복습</a><a href="review-vocab.html">📚 누적 표현 →</a></div>
<div class="container">

  <div class="card"><h2>🎧 오디오 에피소드 <span class="muted" style="font-weight:400">· 진짜 음성 · 매주 자동</span></h2>
    <div id="audio-latest" class="muted">에피소드 불러오는 중…</div>
    <div class="archive" id="audio-archive"></div></div>

  <div class="card"><h2>▶ 바로 듣기 <span class="muted" style="font-weight:400">· 브라우저 음성(즉시·폴백)</span></h2>
    <div class="player">
      <button class="pbtn" id="play">▶ 재생</button>
      <button class="pbtn alt" id="pause">⏸ 일시정지</button>
      <button class="pbtn alt" id="resume">▶ 이어듣기</button>
      <button class="pbtn alt" id="stop">⏹ 처음부터</button>
      <label class="speed">속도 <input type="range" id="rate" min="0.7" max="1.3" step="0.1" value="1"> <span id="rv">1.0x</span></label>
    </div>
    <div class="muted" id="ttswarn" style="margin-bottom:8px"></div>
    <div class="stage" id="stage"></div>
  </div>

  <div class="card"><h2>💬 이 내용으로 AI와 이야기하기</h2>
    <div class="muted" style="margin-bottom:10px">클릭하면 이번 주 요약 프롬프트가 복사되고 Gemini가 열립니다. 붙여넣고 대화하세요.</div>
    <div class="modes">
      <div class="mode" onclick="copyOpen('chat')"><span class="ico">💬</span>튜터 대화<span class="sub">약점 집중 연습</span></div>
      <div class="mode" onclick="copyOpen('lecture')"><span class="ico">🎓</span>강의식 설명<span class="sub">규칙+예문+퀴즈</span></div>
      <div class="mode" onclick="copyOpen('radio')"><span class="ico">🎙</span>라디오 인터뷰<span class="sub">게스트 롤플레이</span></div>
    </div>
  </div>

  <div class="foot">대본: scripts/build_radio.py · 음성: 브라우저 Web Speech(무료) · 매주 금요일 Claude 갱신</div>
</div>

<pre id="radio-src" hidden>{esc(src)}</pre>
<div class="toast" id="toast">✅ 복사됐어요! Gemini에 붙여넣으세요</div>
<script>
const PROMPTS={{chat:{P['chat']},lecture:{P['lecture']},radio:{P['radio']}}};
function showToast(m){{const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2500);}}
function copyOpen(mode){{const txt=PROMPTS[mode]||'';const go=()=>{{showToast('✅ 복사됐어요! Gemini에 붙여넣으세요');setTimeout(()=>window.open('https://gemini.google.com/app','_blank'),600);}};navigator.clipboard.writeText(txt).then(go).catch(()=>{{const a=document.createElement('textarea');a.value=txt;document.body.appendChild(a);a.select();document.execCommand('copy');a.remove();go();}});}}

// ── 라디오 플레이어 (Web Speech API) ──
const RAW=document.getElementById('radio-src').textContent.trim();
const LINES=RAW.split('\\n').map(l=>l.trim()).filter(Boolean).map(l=>{{const i1=l.indexOf('|'),i2=l.indexOf('|',i1+1);return{{sp:l.slice(0,i1),lang:l.slice(i1+1,i2),text:l.slice(i2+1)}};}});
const stage=document.getElementById('stage');
LINES.forEach((ln,i)=>{{const d=document.createElement('div');d.className='bubble '+(ln.sp==='민지'?'mc':'coach');d.dataset.idx=i;d.innerHTML='<span class="who">'+ln.sp+'</span>'+ln.text;stage.appendChild(d);}});
const synth=window.speechSynthesis;
let voices=[],koV=null,enV=null;
function pickVoices(){{voices=synth?synth.getVoices():[];koV=voices.find(v=>v.lang&&v.lang.toLowerCase().startsWith('ko'))||null;enV=voices.find(v=>v.lang&&v.lang.toLowerCase().startsWith('en'))||null;}}
if(synth){{pickVoices();synth.onvoiceschanged=pickVoices;}}
let idx=0,playing=false,rate=1;
function highlight(i){{document.querySelectorAll('.bubble').forEach(b=>b.classList.toggle('on',(+b.dataset.idx)===i));const el=document.querySelector('.bubble.on');if(el)el.scrollIntoView({{block:'center',behavior:'smooth'}});}}
function speakAt(i){{if(!synth||i>=LINES.length){{playing=false;highlight(-1);idx=0;return;}}idx=i;highlight(i);const ln=LINES[i];const u=new SpeechSynthesisUtterance(ln.text);u.lang=ln.lang==='ko'?'ko-KR':'en-US';const v=ln.lang==='ko'?koV:enV;if(v)u.voice=v;u.rate=rate;u.pitch=ln.sp==='민지'?1.15:0.85;u.onend=()=>{{if(playing)speakAt(i+1);}};synth.speak(u);}}
document.getElementById('play').onclick=()=>{{if(!synth){{document.getElementById('ttswarn').textContent='이 브라우저는 음성 재생을 지원하지 않아요. 대본을 읽어주세요.';return;}}if(playing)return;playing=true;synth.cancel();speakAt(idx>=LINES.length?0:idx);}};
document.getElementById('pause').onclick=()=>{{if(synth&&synth.speaking)synth.pause();}};
document.getElementById('resume').onclick=()=>{{if(synth)synth.resume();}};
document.getElementById('stop').onclick=()=>{{playing=false;if(synth)synth.cancel();idx=0;highlight(-1);}};
const rE=document.getElementById('rate');rE.oninput=()=>{{rate=parseFloat(rE.value);document.getElementById('rv').textContent=rate.toFixed(1)+'x';}};
if(!synth)document.getElementById('ttswarn').textContent='⚠️ 이 브라우저는 음성 합성을 지원하지 않아 대본만 표시됩니다.';

// ── 오디오 에피소드 (radio/episodes.json 클라이언트 fetch) ──
fetch('radio/episodes.json',{{cache:'no-store'}}).then(r=>r.ok?r.json():[]).then(eps=>{{
  const L=document.getElementById('audio-latest'),A=document.getElementById('audio-archive');
  if(!Array.isArray(eps)||!eps.length){{L.textContent='아직 오디오 에피소드가 없어요. 아래 ▶ 바로 듣기(브라우저 음성)로 들어보세요.';return;}}
  const top=eps[0];
  L.innerHTML='<div class="epweek">'+top.week+' · '+(top.date||'')+'</div><audio controls preload="none" src="radio/'+top.file+'"></audio>';
  A.innerHTML=eps.slice(1).map(e=>'<a href="radio/'+e.file+'">🎧 '+e.week+' ('+(e.date||'')+')</a>').join('');
}}).catch(()=>{{document.getElementById('audio-latest').textContent='오디오 목록을 불러오지 못했어요.';}});
</script>
</body></html>"""


def build():
    lessons = W.load_all()
    if not lessons:
        print("ℹ️ 분석 가능한 수업 없음 — radio 생략")
        return
    carrot_map = W.load_carrot()
    weeks = OrderedDict()
    for l in lessons:
        weeks.setdefault(l["iso"], []).append(l)
    wk_iso = max(weeks.keys())          # 가장 최근 주
    wk = weeks[wk_iso]
    script_lines = build_script(wk_iso, wk, lessons, carrot_map)
    prompts = build_chat_prompts(wk_iso, wk, lessons, carrot_map)
    page = render(wk_iso, script_lines, prompts)
    open(os.path.join(DOCS, "radio.html"), "w", encoding="utf-8").write(page)
    print(f"✅ docs/radio.html 생성 · {W.week_label(wk_iso)} · 대본 {len(script_lines)}줄")


if __name__ == "__main__":
    build()

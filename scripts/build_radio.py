#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎙️ 영어 주간 라디오 생성기 / Weekly English radio page (주차별 누적).

누적 피드백(AI 일일 + 강사 공식 + 약점·어휘)에서 '라디오 담화 대본'을 만들고,
주차마다 자기완결형 페이지로 렌더한다 (주간 복습 model B 와 동일한 누적 구조):
  docs/radio-2026-Www.html  ← 주마다 1개(영구 누적, 브라우저 음성으로 청취 가능)
  docs/radio.html           ← 허브 = 가장 최근 주 + 🗂 주차별 기록 목록 + 오디오 에피소드

페이지는 브라우저 Web Speech API(speechSynthesis)로 대본을 두 진행자(민지=MC,
알렉스=코치) 음성으로 읽어준다 — 서버·오디오파일·비용 0. 실제 MP3(build_radio_audio.py)는
radio/episodes.json 으로 주차별 누적되며, 각 페이지는 '자기 주차' 에피소드를 표시한다.
대화/강의/라디오 인터뷰 3가지 'AI와 대화' 모드 프롬프트(클릭→복사→Gemini)도 포함.

설계:
  - 대본은 규칙기반 폴백으로 항상 채워진다(파일이 깨지지 않음).
  - <pre id="radio-src"> 안의 'speaker|lang|text' 라인이 단일 진실원천(SSOT).
    금요일 루틴의 Claude가 허브(radio.html=현재 주)의 이 내용을 더 자연스러운 담화로
    교체 가능(없어도 동작). 과거 주차 페이지는 규칙기반 스냅샷으로 유지된다
    (주간 복습의 종합문과 동일한 트레이드오프).

CLI:  python3 scripts/build_radio.py   # 전체 주차 생성(백필) + 허브
"""
import os, sys, html, datetime, re
import json as _json
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_weekly_review as W  # 데이터 파싱 재사용 (load_all/load_carrot/avg_score/week_*)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")


def radio_week_file(iso):
    """주차 → 라디오 스냅샷 파일명. radio-2026-W26.html"""
    return f"radio-{W.week_label(iso)}.html"


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


# ───────── 카테고리별 '왜 / 문화 / 팁' 인사이트 (규칙기반 심층화) ─────────
# 정규화 라벨(build_weekly_review.norm_grammar)에 substring 매칭.
# why_ko 는 한국어 음성으로 읽혀 '왜 그런지'를 학습자가 확실히 이해하게 한다.
INSIGHTS = [
    ("Article", {
        "why_en": "Korean has no a, an, or the, so articles feel optional. But in English they quietly tell the listener whether you mean one-of-many or the specific one we both already know.",
        "why_ko": "한국어에는 관사가 없어서 a, an, the가 사소해 보여요. 하지만 영어에서는 '여럿 중 하나'인지, '우리 둘 다 아는 바로 그것'인지를 관사가 정해 줍니다.",
        "tip_en": "Quick test: a brand-new thing gets a or an. A thing we both already know gets the."}),
    ("Preposition", {
        "why_en": "Prepositions almost never map one-to-one between Korean and English, so the same Korean ending can become in, on, at, or to depending on the picture in your head.",
        "why_ko": "전치사는 한국어와 일대일로 안 맞아요. 같은 '에, 에서'가 머릿속 그림에 따라 in, on, at, to로 갈립니다.",
        "tip_en": "Picture it: a point gets at, a surface gets on, an enclosed space gets in."}),
    ("Subject", {  # Subject–Verb Agreement / Missing Subjects
        "why_en": "Korean verbs don't change for he, she, or it, and Korean often drops the subject entirely. English keeps the subject and adds an s for he, she, it.",
        "why_ko": "한국어 동사는 그, 그녀, 그것이어도 형태가 안 변하고 주어를 자주 생략하죠. 영어는 주어를 꼭 두고 3인칭 단수엔 s를 붙여요.",
        "tip_en": "He, she, it — add an s. Say it like a reflex every single time."}),
    ("Verb Form", {
        "why_en": "English packs a lot into the verb — tense, the helper do or have, the right ending. Korean spreads that meaning across other words, so the English verb form is easy to slip on.",
        "why_ko": "영어는 동사 하나에 시제, do나 have 같은 조동사, 어미까지 다 담아요. 한국어는 그 의미를 여러 단어로 나눠서, 영어 동사 형태에서 자주 실수가 나요.",
        "tip_en": "Lock the helper first — do, does, did, have — then the main verb just stays simple."}),
    ("Tense", {
        "why_en": "Korean often shows time with words like yesterday or already, while English bakes the time right into the verb itself.",
        "why_ko": "한국어는 '어제, 이미' 같은 시간 단어로 때를 나타내지만, 영어는 동사 자체에 시제를 넣습니다.",
        "tip_en": "If it's finished and past, let the verb show it: go becomes went, eat becomes ate."}),
    ("Gerund", {
        "why_en": "After certain verbs and all prepositions, English wants the -ing form, not the dictionary verb. There's no equivalent rule in Korean, so it feels random until you hear it enough.",
        "why_ko": "특정 동사 뒤와 모든 전치사 뒤에서 영어는 동사원형이 아니라 -ing 형을 원해요. 한국어엔 없는 규칙이라 많이 들어야 익숙해져요.",
        "tip_en": "After a preposition, always -ing: good at cooking, interested in learning."}),
    ("Determiner", {
        "why_en": "Much, many, some, any, a few — English changes the word depending on whether you can count the noun. Korean doesn't force that choice, so it's an easy place to wobble.",
        "why_ko": "much, many, some, any처럼 영어는 셀 수 있는 명사냐 아니냐에 따라 단어를 바꿔요. 한국어는 그 구분을 강요하지 않아서 흔들리기 쉬워요.",
        "tip_en": "Can you count it? Use many. Can't count it, like water or time? Use much."}),
]
DEFAULT_INSIGHT = {
    "why_en": "Most repeated mistakes aren't about vocabulary — they're tiny habits from translating Korean word-for-word. The fix is noticing the pattern, which you're doing right now.",
    "why_ko": "반복되는 실수는 대부분 단어 문제가 아니라, 한국어를 그대로 직역하는 작은 습관에서 나와요. 해결책은 패턴을 알아채는 것 — 지금 하고 있는 그거예요.",
    "tip_en": "Pick one pattern a week and hunt for it. Awareness alone fixes half of it."}

# 흥미 코너: 어원·관용구·문화 대비 이야기(주차마다 회전 → 지루함 방지).
FUN_FACTS = [
    ("Here's a fun one. The word OK might be the most spoken word on Earth, and it began as a silly joke abbreviation in 1830s Boston newspapers for all correct, spelled wrong on purpose.",
     "오늘의 흥미 코너예요. OK는 지구에서 가장 많이 쓰이는 말일 수도 있는데, 1830년대 보스턴 신문에서 일부러 틀리게 쓴 농담 줄임말에서 시작됐대요."),
    ("In English we say break a leg to wish someone good luck before a performance. Actors believed that wishing real luck would jinx it, so they flipped it around.",
     "영어로 공연 전엔 행운을 빌 때 다리를 부러뜨리라고 해요. 배우들은 진짜 행운을 빌면 오히려 망친다고 믿어서 반대로 말한 거죠."),
    ("Quick culture note. Koreans cheer fighting, but native speakers don't use it that way. Instead they say you've got this, or go for it, or you can do it.",
     "문화 한 가지. 한국에선 '화이팅'이라고 외치지만, 원어민은 그렇게 안 써요. 대신 you've got this, go for it, you can do it 라고 해요."),
    ("Ever wonder why we eat beef but raise a cow? After 1066, French-speaking nobles named the food on the table, while English-speaking farmers named the animal in the field.",
     "소는 cow인데 고기는 왜 beef일까요? 1066년 이후 식탁의 음식은 프랑스어를 쓰던 귀족이, 들판의 동물은 영어를 쓰던 농부가 이름 붙였기 때문이에요."),
    ("The word deadline sounds dramatic for a reason. It first meant a line drawn in a prison that prisoners could not cross. Now it's just your Friday afternoon at work.",
     "deadline이 괜히 무섭게 들리는 게 아니에요. 원래는 감옥에서 죄수가 넘으면 안 되는 선을 뜻했어요. 지금은 그냥 금요일 오후 마감이죠."),
    ("Here's an idiom worth stealing. When something is very easy, native speakers say it's a piece of cake. So next time a lesson clicks, just smile and say, that was a piece of cake.",
     "훔쳐 쓸 만한 관용구 하나. 아주 쉬울 때 원어민은 a piece of cake라고 해요. 다음에 수업이 쉽게 풀리면 웃으며 that was a piece of cake 라고 해보세요."),
]


def _insight_for(top):
    for key, ins in INSIGHTS:
        if key.lower() in (top or "").lower():
            return ins
    return DEFAULT_INSIGHT


def build_script(wk_iso, wk, lessons, carrot_map):
    """규칙기반 '심층' 라디오 대본 → [(speaker, lang, text), ...].
    단순 교정 나열을 넘어 ① 왜 틀렸는지(why) ② 문화/대비(culture) ③ 흥미 코너를
    세그먼트로 엮어 지루하지 않게 구성한다. lessons = 그 주말까지 누적.
    (금요일 루틴의 Claude가 허브 #radio-src 를 실제 데이터 기반 더 깊은 담화로 교체.)"""
    ai_pairs = [p for l in wk for p in l["pairs"] if p.get("said") and p.get("natural")]
    vocab = [v for l in wk for v in l["vocab"] if v.get("word")]
    wk_dates = {l["date"] for l in wk}
    cpairs = [c for c in carrot_pairs_for_dates(carrot_map, wk_dates)
              if c.get("original") and c.get("better")]
    weak = Counter(l["grammar_norm"] for l in lessons).most_common()
    top = weak[0][0] if weak else "문법"
    topn = weak[0][1] if weak else 0
    second = weak[1][0] if len(weak) > 1 else None
    avg = W.avg_score(lessons)
    ins = _insight_for(top)
    fun_en, fun_ko = FUN_FACTS[(wk_iso[1] if isinstance(wk_iso, tuple) else 0) % len(FUN_FACTS)]

    L = []
    add = lambda s, lang, t: L.append((s, lang, _clean1(t)))
    wl = W.week_label(wk_iso)

    # 1) 인트로 — 이번 주를 '이야기'로 연다
    add("민지", "en", "Hello and welcome back to your Weekly English Radio. I'm Minji, your host.")
    add("알렉스", "en", f"And I'm Alex, your coach. This is {wl}, and you spoke in {len(wk)} lessons this week. Let's not just list your mistakes today, let's understand them.")
    add("민지", "en", f"Our headline pattern is {top}. It has shown up {topn} times so far. Alex, why does this one keep coming back?")

    # 2) Why It Happens — 깊이 1단(왜 + 한국어 설명 + 문화 대비 + 팁)
    add("알렉스", "en", "Great question. " + ins["why_en"])
    add("민지", "ko", ins["why_ko"])
    add("알렉스", "en", ins["tip_en"])
    if ai_pairs:
        add("민지", "en", "Let's hear that in your own words. Here are a few sentences you actually said, and the natural version.")
        for p in ai_pairs[:4]:
            add("알렉스", "en", f"You said: {p['said']}")
            add("민지", "en", f"More naturally: {p['natural']}")
        add("알렉스", "en", "Hear the small shifts? Same idea, just the English habit on top.")

    # 3) Correction Clinic — 나머지 교정(간결)
    rest = ai_pairs[4:14]
    if rest:
        add("민지", "en", "Time for the Correction Clinic. Quick-fire, repeat after us if you can.")
        for p in rest:
            add("알렉스", "en", f"You said: {p['said']}")
            add("민지", "en", f"Better: {p['natural']}")

    # 4) 강사 교정
    if cpairs:
        add("알렉스", "en", "Your tutor also marked a few this week. These came straight from your live lessons.")
        for cp in cpairs[:6]:
            add("민지", "en", f"Instead of: {cp['original']}")
            add("알렉스", "en", f"Say: {cp['better']}")

    # 5) Vocabulary in Context — 단어 + 쓰임 한 마디
    if vocab:
        add("민지", "en", "Now, Vocabulary in Context. Not just the word, but how it lives in a sentence.")
        for v in vocab[:6]:
            tail = f" It means {v['meaning']}." if v.get("meaning") else ""
            add("알렉스", "en", f"Word to keep: {v['word']}.{tail} Try saying one real sentence with it today.")

    # 6) Culture Corner / Did You Know — 흥미 이야기(회전)
    add("민지", "en", "Before we wrap, let's stretch a little beyond the corrections.")
    add("알렉스", "en", fun_en)
    add("민지", "ko", fun_ko)

    # 7) Recap + Mission + Outro
    trend = "climbing" if avg >= 7.5 else ("steady" if avg >= 6.5 else "warming up")
    add("알렉스", "en", f"Quick recap. Your fluency average is {avg:.1f} out of ten, and it's {trend}. That's real progress.")
    mission = f"This week, hunt for {top} every time you speak"
    if second:
        mission += f", and keep half an eye on {second}"
    add("민지", "en", mission + ". Awareness first, perfection later.")
    add("알렉스", "en", "That's all for this episode. Have a wonderful week, keep talking, and don't fear mistakes.")
    add("민지", "en", "They're just English habits waiting to click. See you next Friday. Bye for now!")
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
.weeklist{display:flex;flex-direction:column;gap:6px;margin-top:4px}
.weekrow{display:flex;align-items:center;gap:10px;font-size:13px;color:#cbd5e1;text-decoration:none;padding:11px 13px;background:#0f0f13;border:1px solid rgba(255,255,255,.06);border-radius:10px}
.weekrow:hover{border-color:rgba(167,139,250,.4);color:#a78bfa}
.weekrow.active{border-color:rgba(167,139,250,.5);background:#1e1b2e}
.weekrow .wk{font-weight:700;color:#a78bfa;white-space:nowrap}
.weekrow .wr{color:#64748b}
.weekrow .wk-audio{margin-left:auto;font-size:14px;min-width:18px;text-align:right}
.foot{text-align:center;font-size:11px;color:#475569;margin-top:26px;line-height:1.8}
"""


def _archive_rows(archive, wk_iso):
    out = []
    for a in archive:
        active = " active" if a["iso"] == wk_iso else ""
        cur = " · 현재" if a["iso"] == wk_iso else ""
        out.append(
            f'<a class="weekrow{active}" data-wk="{a["label"]}" href="{a["href"]}">'
            f'<span class="wk">{a["label"]}{cur}</span>'
            f'<span class="wr">{a["range"]} · {a["lessons"]}회</span>'
            f'<span class="wk-audio"></span></a>')
    return "".join(out)


def render(wk_iso, src, prompts, archive, is_hub):
    label = W.week_label(wk_iso)
    rng = W.week_range(wk_iso)
    P = {k: _json.dumps(v, ensure_ascii=False) for k, v in prompts.items()}
    pw = _json.dumps(label, ensure_ascii=False)
    arc_rows = _archive_rows(archive, wk_iso)

    if is_hub:
        ptitle = "🎙️ 영어 주간 라디오"
        htitle = "🎙️ 영어 주간 라디오"
        hsub = f"{label} · {rng} · 매주 자동 갱신"
        nav = '<a href="index.html">← 일일 복습</a><a href="review-vocab.html">📚 누적 표현 →</a>'
    else:
        ptitle = f"🎙️ 라디오 {label}"
        htitle = f"🎙️ 라디오 · {label}"
        hsub = f"{rng} · 주차 기록 · 브라우저 음성으로 청취"
        nav = '<a href="radio.html">← 최신 라디오</a><a href="review-index.html">📚 복습 목록 →</a>'

    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><link rel="manifest" href="manifest.webmanifest"><meta name="theme-color" content="#0f0f13"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="당근영어"><link rel="apple-touch-icon" href="apple-touch-icon.png"><link rel="icon" type="image/png" sizes="192x192" href="icon-192.png"><script src="install-banner.js" defer></script><script src="sw-reg.js" defer></script>
<title>{ptitle}</title><style>{CSS}</style></head><body>
<div class="header"><h1>{htitle}</h1>
<div class="range">{hsub}</div></div>
<div class="nav">{nav}</div>
<div class="container">

  <div class="card"><h2>🎧 오디오 에피소드 <span class="muted" style="font-weight:400">· 진짜 음성 · 이 주차</span></h2>
    <div id="audio-latest" class="muted">에피소드 불러오는 중…</div></div>

  <div class="card"><h2>🗂 주차별 라디오 기록 <span class="muted" style="font-weight:400">· 최신순 · 누적</span></h2>
    <div class="weeklist">{arc_rows}</div></div>

  <div class="card"><h2>▶ 바로 듣기 <span class="muted" style="font-weight:400">· 브라우저 음성(즉시·폴백)</span></h2>
    <div class="player">
      <button class="pbtn" id="play">▶ 재생</button>
      <button class="pbtn alt" id="pause">⏸ 일시정지</button>
      <button class="pbtn alt" id="resume">▶ 이어듣기</button>
      <button class="pbtn alt" id="stop">⏹ 처음부터</button>
      <label class="speed">속도 <input type="range" id="rate" min="0.7" max="1.3" step="0.1" value="1"> <span id="rv">1.0x</span></label>
    </div>
    <div class="muted" id="ttswarn" style="margin-bottom:8px"></div>
    <div class="muted" style="margin:2px 0 10px;font-size:11.5px;line-height:1.7">💡 재생 중에는 화면이 자동으로 꺼지지 않게 막아요(Wake&nbsp;Lock). 다만 직접 화면을 끄면 브라우저 음성은 멈출 수 있어요 — <b>화면을 끈 채 듣고 싶다면 맨 위 🎧 오디오 에피소드(MP3)</b>를 쓰세요. 잠금화면에서도 재생됩니다.</div>
    <div class="stage" id="stage"></div>
  </div>

  <div class="card"><h2>💬 이 내용으로 AI와 이야기하기</h2>
    <div class="muted" style="margin-bottom:10px">클릭하면 이 주차 요약 프롬프트가 복사되고 Gemini가 열립니다. 붙여넣고 대화하세요.</div>
    <div class="modes">
      <div class="mode" onclick="copyOpen('chat')"><span class="ico">💬</span>튜터 대화<span class="sub">약점 집중 연습</span></div>
      <div class="mode" onclick="copyOpen('lecture')"><span class="ico">🎓</span>강의식 설명<span class="sub">규칙+예문+퀴즈</span></div>
      <div class="mode" onclick="copyOpen('radio')"><span class="ico">🎙</span>라디오 인터뷰<span class="sub">게스트 롤플레이</span></div>
    </div>
  </div>

  <div class="foot">대본: scripts/build_radio.py · 음성: 브라우저 Web Speech(무료) · 주차별 누적 · 매주 금요일 Claude 갱신</div>
</div>

<pre id="radio-src" hidden>{esc(src)}</pre>
<div class="toast" id="toast">✅ 복사됐어요! Gemini에 붙여넣으세요</div>
<script>
const PAGE_WEEK={pw};
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
let idx=0,playing=false,rate=1,wakeLock=null;
async function acquireWake(){{try{{if('wakeLock' in navigator){{wakeLock=await navigator.wakeLock.request('screen');wakeLock.addEventListener('release',()=>{{wakeLock=null;}});}}}}catch(e){{}}}}
function releaseWake(){{try{{if(wakeLock){{wakeLock.release();wakeLock=null;}}}}catch(e){{}}}}
function highlight(i){{document.querySelectorAll('.bubble').forEach(b=>b.classList.toggle('on',(+b.dataset.idx)===i));const el=document.querySelector('.bubble.on');if(el)el.scrollIntoView({{block:'center',behavior:'smooth'}});}}
function speakAt(i){{if(!synth||i>=LINES.length){{playing=false;releaseWake();highlight(-1);idx=0;return;}}idx=i;highlight(i);const ln=LINES[i];const u=new SpeechSynthesisUtterance(ln.text);u.lang=ln.lang==='ko'?'ko-KR':'en-US';const v=ln.lang==='ko'?koV:enV;if(v)u.voice=v;u.rate=rate;u.pitch=ln.sp==='민지'?1.15:0.85;u.onend=()=>{{if(playing)speakAt(i+1);}};u.onerror=()=>{{if(playing)setTimeout(()=>speakAt(i+1),250);}};synth.speak(u);}}
document.getElementById('play').onclick=()=>{{if(!synth){{document.getElementById('ttswarn').textContent='이 브라우저는 음성 재생을 지원하지 않아요. 대본을 읽어주세요.';return;}}if(playing)return;playing=true;acquireWake();synth.cancel();speakAt(idx>=LINES.length?0:idx);}};
document.getElementById('pause').onclick=()=>{{if(synth&&synth.speaking)synth.pause();}};
document.getElementById('resume').onclick=()=>{{if(synth){{synth.resume();if(playing)acquireWake();}}}};
document.getElementById('stop').onclick=()=>{{playing=false;releaseWake();if(synth)synth.cancel();idx=0;highlight(-1);}};
document.addEventListener('visibilitychange',()=>{{if(document.visibilityState==='visible'&&playing){{if(synth)synth.resume();acquireWake();}}}});
const rE=document.getElementById('rate');rE.oninput=()=>{{rate=parseFloat(rE.value);document.getElementById('rv').textContent=rate.toFixed(1)+'x';}};
if(!synth)document.getElementById('ttswarn').textContent='⚠️ 이 브라우저는 음성 합성을 지원하지 않아 대본만 표시됩니다.';

// ── 오디오 에피소드: 이 페이지의 주차(PAGE_WEEK) MP3 표시 + 목록에 🎧 뱃지 ──
fetch('radio/episodes.json',{{cache:'no-store'}}).then(r=>r.ok?r.json():[]).then(eps=>{{
  if(!Array.isArray(eps))eps=[];
  eps.forEach(e=>{{const row=document.querySelector('.weekrow[data-wk="'+e.week+'"] .wk-audio');if(row)row.textContent='🎧';}});
  const L=document.getElementById('audio-latest');
  const mine=eps.find(e=>e.week===PAGE_WEEK);
  if(mine){{
    L.innerHTML='<div class="epweek">'+mine.week+' · '+(mine.date||'')+'</div><audio id="ep-audio" controls preload="none" src="radio/'+mine.file+'"></audio>';
    const au=document.getElementById('ep-audio');
    // 잠금화면/화면 꺼짐에서도 재생 + 컨트롤 노출(MediaSession). 진짜 음성 파일이라 백그라운드 OK.
    if(au&&'mediaSession' in navigator){{
      try{{navigator.mediaSession.metadata=new MediaMetadata({{title:'영어 주간 라디오 '+mine.week,artist:'민지 & 알렉스 · 당근영어',album:'Weekly English Radio'}});}}catch(e){{}}
      try{{navigator.mediaSession.setActionHandler('play',()=>au.play());navigator.mediaSession.setActionHandler('pause',()=>au.pause());}}catch(e){{}}
    }}
  }}
  else{{L.textContent='이 주차 오디오(MP3)는 아직 없어요. 아래 ▶ 바로 듣기(브라우저 음성)로 들어보세요.';}}
}}).catch(()=>{{document.getElementById('audio-latest').textContent='오디오 목록을 불러오지 못했어요. 아래 ▶ 바로 듣기로 들어보세요.';}});
</script>
</body></html>"""


def _lines_to_src(lines):
    return "\n".join(f"{s}|{lang}|{t}" for s, lang, t in lines)


def _extract_src_and_week(path):
    """기존 페이지에서 (#radio-src 내부 원문, PAGE_WEEK) 추출. 없으면 (None, None)."""
    if not os.path.exists(path):
        return None, None
    try:
        t = open(path, encoding="utf-8").read()
    except OSError:
        return None, None
    m = re.search(r'<pre id="radio-src"[^>]*>(.*?)</pre>', t, re.S)
    src = html.unescape(m.group(1)).strip() if m else None
    mw = re.search(r'const PAGE_WEEK="([^"]+)"', t)
    return (src or None), (mw.group(1) if mw else None)


def resolve_src(iso, is_hub, default_src):
    """대본 보존 정책 — '주차별 기록'이 규칙기반 재생성에 덮이지 않게:
      1) 대상 파일이 이미 같은 주(label) 대본을 갖고 있으면 그대로 보존(=Claude 심층본 freeze).
      2) 과거주 페이지인데 허브(radio.html)가 마침 이 주였다면(롤오버) 허브 대본을 승격.
      3) 그 외에는 규칙기반 default 사용.
    → 호출 시점에 과거주 루프가 허브보다 먼저 돌아야 승격이 성립(아래 build 순서 보장)."""
    label = W.week_label(iso)
    target = os.path.join(DOCS, "radio.html" if is_hub else radio_week_file(iso))
    src, wk = _extract_src_and_week(target)
    if src and wk == label:
        return src
    if not is_hub:
        hub_src, hub_wk = _extract_src_and_week(os.path.join(DOCS, "radio.html"))
        if hub_src and hub_wk == label:
            return hub_src
    return default_src


def build():
    lessons = W.load_all()
    if not lessons:
        print("ℹ️ 분석 가능한 수업 없음 — radio 생략")
        return
    carrot_map = W.load_carrot()
    weeks = OrderedDict()
    for l in lessons:
        weeks.setdefault(l["iso"], []).append(l)
    ordered = sorted(weeks.keys())
    latest = ordered[-1]

    # 아카이브 메타(최신순). 최신 주는 허브 radio.html, 과거 주는 radio-Www.html.
    archive = []
    for iso in sorted(weeks.keys(), reverse=True):
        label = W.week_label(iso)
        archive.append({
            "iso": iso, "label": label, "range": W.week_range(iso),
            "lessons": len(weeks[iso]),
            "href": "radio.html" if iso == latest else radio_week_file(iso),
        })

    # 과거 주차 스냅샷 페이지(영구 누적). 허브보다 먼저 돌려 롤오버 승격을 보장.
    n_week = 0
    for iso in ordered:
        if iso == latest:
            continue
        wk = weeks[iso]
        cum = [l for l in lessons if l["iso"] <= iso]      # 그 주말까지 누적
        default_src = _lines_to_src(build_script(iso, wk, cum, carrot_map))
        src = resolve_src(iso, False, default_src)
        prompts = build_chat_prompts(iso, wk, cum, carrot_map)
        page = render(iso, src, prompts, archive, is_hub=False)
        open(os.path.join(DOCS, radio_week_file(iso)), "w", encoding="utf-8").write(page)
        n_week += 1

    # 허브 = 가장 최근 주(라이브·Claude 갱신 대상·오디오 소스)
    wk = weeks[latest]
    default_src = _lines_to_src(build_script(latest, wk, lessons, carrot_map))
    src = resolve_src(latest, True, default_src)
    prompts = build_chat_prompts(latest, wk, lessons, carrot_map)
    page = render(latest, src, prompts, archive, is_hub=True)
    open(os.path.join(DOCS, "radio.html"), "w", encoding="utf-8").write(page)

    print(f"✅ radio.html(허브={W.week_label(latest)}) + 주차 스냅샷 {n_week}개 · 허브 대본 {len(src.splitlines())}줄")
    for a in archive:
        tag = " (허브/현재)" if a["iso"] == latest else ""
        print(f"   {a['href']}  {a['lessons']}회{tag}")
    print(f"CURRENT_RADIO_FILE=radio.html")
    print(f"CURRENT_RADIO_WEEK={W.week_label(latest)}")


if __name__ == "__main__":
    build()

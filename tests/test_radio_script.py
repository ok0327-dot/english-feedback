#!/usr/bin/env python3
"""
주간 라디오 규칙기반 대본 검사 / tests for scripts/build_radio.py build_script (2026-11-16 라디오쇼 개편).

검사 내용 / what is checked:
  - 형식: 모든 줄이 '민지|알렉스' · 'en|ko' · 빈 글 없음 · 글 안에 '|' 없음 · 빈 줄 없음
  - 한국어(ko) 줄 비율 30% 이하 · 200줄 이하(오디오 무료 한도)
  - 최소 분량 120줄 이상(보충 코너) — 예외는 '얇은 주'(교정 < THIN_WEEK_ITEMS)뿐이고, 그땐 짧은 회차 안내 줄이 있다
  - 같은 줄 되풀이 금지: 바로 앞 줄과 똑같은 줄 없음 · 어떤 줄도 세 번 이상 안 나옴
  - 강사(carrot) 데이터가 있으면 Tutor Rewind(요일 + 수업 주제 + 퀴즈) + 교정마다 '한 줄 정리' ko 줄
  - 강사 데이터가 없는 주도 대본이 정상(AI 교정으로 Rewind)
  - 학습자 문장은 입력 데이터에 있는 것만(지어내지 않음) · 문법책 용어 없음 · 같은 입력 → 같은 대본
  - 페이지로 렌더한 뒤 플레이어/오디오(build_radio_audio.parse_radio_html)가 같은 줄을 읽음
실행 / run:  python3 tests/test_radio_script.py   (pytest 불필요, 네트워크 미사용)
"""
import os
import re
import sys
import tempfile
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import build_radio as R  # noqa: E402
import build_weekly_review as W  # noqa: E402

ISO = (2026, 46)
WK = [
    {"date": "2026-11-09", "iso": ISO, "topic": "Discussing local community events and volunteering opportunities.",
     "grammar": "Subject-Verb Agreement", "grammar_norm": "Subject–Verb Agreement", "score": 7.0,
     "pairs": [{"said": "If this apartment have a big event, we see the board.", "natural": "If this apartment has a big event, we see the board."},
               {"said": "I go there yesterday with my wife.", "natural": "I went there yesterday with my wife."}],
     "vocab": [{"word": "give back", "pos": "phrase", "meaning": "환원하다, 봉사하다"}]},
    {"date": "2026-11-11", "iso": ISO, "topic": "Rubbish, Recycling, and Waste Disposal in Daily Life",
     "grammar": "Prepositions", "grammar_norm": "Prepositions", "score": 6.5,
     "pairs": [{"said": "I put the bottle at the bin.", "natural": "I put the bottle in the bin."},
               {"said": "It is so hard to deal the trash here.", "natural": "Dealing with trash here is such a hassle."}],
     "vocab": [{"word": "hazardous", "pos": "adj", "meaning": "위험한, 유해한"}]},
    {"date": "2026-11-13", "iso": ISO, "topic": "Daily Routines and Weekend Plans",
     "grammar": "Verb Tense", "grammar_norm": "Verb Tense", "score": 7.5,
     "pairs": [{"said": "Last weekend I watch a movie with my son.", "natural": "Last weekend I watched a movie with my son."}],
     "vocab": [{"word": "commute", "pos": "verb", "meaning": "통근하다"}]},
]
CARROT = {
    "2026-11-09": [{"original": "Are there any good news?", "better": "Is there any good news?"},
                   {"original": "He hold the step", "better": "He is standing on the stepladder"},
                   {"original": "Heads UP!", "better": "Alternative:  Just to let you know..."}],
    "2026-11-10": [{"original": "Did you HAPPEN (pronounced HAF-FEN) to see the notice?", "better": "Did you HAPPEN (pronounced HAP-PEN) to see the notice?"},
                   {"original": "Tax deduction: An amount DAT LOWER how much tax you owe.", "better": "Tax deduction: An amount THAT LOWER(S) how much tax you owe."},
                   {"original": "I changed the part that pours water", "better": "I changed my showerhead"}],
    "2026-11-11": [{"original": "It is same to Korea", "better": "It is the same as Korea"},
                   {"original": "I'm so drowsiness.", "better": "I'm so drowsy."}],
    "2026-11-13": [{"original": "I come back my office", "better": "I came back to my office"}],
}
MEMOS = {"2026-11-10": "Today we discussed building notices and fire drills. Here are today's notes:"}

EN_JARGON = ["participle", "infinitive", "gerund", "third-person", "third person", "uncountable", "countable",
             "article", "preposition", "auxiliary", "base form", "pronoun", "passive", "present perfect", "modal",
             "tense", "plural", "singular", "noun", "adjective", "adverb", "determiner", "quantifier", "clause"]
KO_JARGON = ["과거분사", "p.p", "부정사", "동명사", "동사원형", "3인칭", "단수", "복수", "가산", "관계대명사",
             "목적어", "수동태", "현재완료", "조동사", "관사", "전치사", "시제", "주어", "동사", "형용사", "부사", "명사"]


def format_problems(lines):
    bad = []
    for s, lang, t in lines:
        if s not in ("민지", "알렉스") or lang not in ("en", "ko") or not t.strip() or "|" in t or "\n" in t:
            bad.append((s, lang, t))
    src = R._lines_to_src(lines)
    for ln in src.split("\n"):
        p = ln.split("|", 2)
        if len(p) != 3 or not ln.strip():
            bad.append(("raw", "", ln))
    return bad


def repeat_problems(lines):
    """같은 줄 되풀이: 바로 앞 줄과 똑같은 줄 + 세 번 이상 나온 줄."""
    texts = [t for _, _, t in lines]
    consec = [t for a, t in zip(texts, texts[1:]) if a == t]
    many = sorted(t for t, c in Counter(texts).items() if c > 2)
    return consec + many


def is_thin(iso, wk, cmap, memos):
    mat = R.week_material(iso, wk, cmap, memos)
    return len(mat["tutor"]) + len(mat["ai"]) < R.THIN_WEEK_ITEMS


def jargon_hits(lines):
    return [(w, t) for _, lang, t in lines for w in (EN_JARGON if lang == "en" else KO_JARGON)
            if (re.search(r"\b" + re.escape(w) + r"\b", t.lower()) if lang == "en" else w in t)]


def main():
    failures = []

    def check(label, cond):
        print(("PASS " if cond else "FAIL ") + label)
        if not cond:
            failures.append(label)

    lines = R.build_script(ISO, WK, WK, CARROT, MEMOS)
    texts = [t for _, _, t in lines]
    n, ko, ratio = R.script_stats(lines)
    print(f"   (synthetic W46: {n} lines, ko {ko} = {ratio:.0%})")

    # 1) 형식
    check("형식: 진행자·언어·빈 글·'|' 없음", not format_problems(lines))
    check("ko 비율 30% 이하", ratio <= 0.30)
    check("ko 줄이 한국어 상기용으로 충분(10% 이상)", ratio >= 0.10)
    check("200줄 이하(오디오 무료 한도)", n <= 200)
    check(f"최소 분량 {R.RADIO_MIN_LINES}줄 이상(스펙 120~200줄)", n >= R.RADIO_MIN_LINES)
    check("같은 줄 되풀이 없음(연속 중복 없음 · 세 번 이상 없음)", not repeat_problems(lines))
    if repeat_problems(lines):
        print("   repeats:", repeat_problems(lines)[:3])

    # 2) 라디오 장치: 스테이션 ID · 콜드 오픈 · 사인오프
    check("스테이션 ID(첫 줄 Joey FM)", "Joey FM" in texts[0])
    check("콜드 오픈 티저(요일 + stay tuned)", any("caught one sentence you said on Monday" in t and "Stay tuned" in t for t in texts[:3]))
    check("사인오프에 Joey FM", any("Joey FM" in t for t in texts[-3:]))

    # 3) Tutor Rewind: 요일 + 주제 + 퀴즈 + 강사 교정 + 한 줄 정리
    check("Tutor Rewind 코너 존재", any("Tutor Rewind" in t for t in texts))
    fix_idx = [i for i, t in enumerate(texts) if t.startswith("Here's your tutor's fix")]
    check("강사 교정 2~4개", 2 <= len(fix_idx) <= 4)
    rw_first = next(i for i, t in enumerate(texts) if "Tutor Rewind" in t)
    check("Tutor Rewind 가 쇼 앞부분(첫 15줄 안)", rw_first < 15)
    check("장면 설정: 요일 + 그날 수업 주제",
          any(t.startswith("Rewind to Monday. You were talking about local community events") for t in texts))
    check("퀴즈 카운트다운(three, two, one)", all("Three, two, one" in texts[i - 1] for i in fix_idx))
    ok_ko = True
    for k, i in enumerate(fix_idx):
        end = fix_idx[k + 1] if k + 1 < len(fix_idx) else len(lines)
        block = lines[i:end]
        if not any(lang == "ko" and t.startswith("한 줄 정리") and re.search(r"[월화수목금토일]요일에", t) for _, lang, t in block):
            ok_ko = False
    check("강사 교정마다 바로 뒤 '한 줄 정리' ko 줄(요일 포함)", ok_ko)
    check("강사+AI 공통 지적 언급", any("your AI coach flagged" in t for t in texts))
    check("발음·용어 낭독 연습은 교정으로 안 씀", not any("HAF-FEN" in t or "Tax deduction" in t or "pronounced" in t.lower() for t in texts))
    check("강사 'Alternative' 표현은 보너스 팁으로", any(t.startswith("Bonus tip from your tutor") and "Just to let you know" in t for t in texts))

    # 4) 게임 · 중간 정리 · 3줄 요약
    games = [g for g in ("Mistake Top 3 Countdown", "Spot the Mistake", "Real or Wrong", "Fix it in Three Seconds") if any(g in t for t in texts)]
    check("게임 1~2개", 1 <= len(games) <= 2)
    check("한국어 중간 정리(2줄 이상)", sum(1 for _, lang, t in lines if lang == "ko" and t.startswith("중간 정리")) >= 2)
    ko_tail = [t for _, lang, t in lines if lang == "ko"]
    check("한국어 3줄 요약(하나·둘·셋)", any(t.startswith("하나,") for t in ko_tail) and any(t.startswith("둘,") for t in ko_tail) and any(t.startswith("셋,") for t in ko_tail))
    def at(s):
        return next((i for i, t in enumerate(texts) if s in t), -1)
    order = [at("Tutor Rewind"), at("It's game time") if at("It's game time") >= 0 else at("Mistake Top 3"),
             at("Why It Happens"), at("halfway through the show"), at("Culture Corner"),
             at("three-line summary in Korean"), at("Your mission for next week")]
    check("런다운 순서: Rewind → 게임 → Why → 중간 정리 → Culture → 3줄 요약 → 미션", all(x >= 0 for x in order) and order == sorted(order))

    # 5) 지어내지 않음: 'you said:' 뒤 문장은 입력 데이터에서만
    real_said = {R._speakable(p["said"]) for l in WK for p in l["pairs"]} | {R._speakable(p["original"]) for ps in CARROT.values() for p in ps}
    quoted = [re.split(r"[Yy]ou said: ", t, 1)[1].split(" Better: ")[0] for t in texts if re.search(r"[Yy]ou said: ", t)]
    check("인용한 학습자 문장은 모두 실제 데이터", quoted and all(q in real_said for q in quoted))

    # 6) 쉬운 말 규칙(문법책 용어 금지) — 합성 데이터엔 그런 단어가 없으니 대본 전체에 나오면 안 된다
    jar = [(w, t) for _, lang, t in lines for w in (EN_JARGON if lang == "en" else KO_JARGON)
           if (re.search(r"\b" + re.escape(w) + r"\b", t.lower()) if lang == "en" else w in t)]
    check("문법책 용어 없음(en·ko)", not jar)
    if jar:
        print("   jargon:", jar[:3])

    # 7) 결정론 + 주차 회전
    check("같은 입력 → 같은 대본", R.build_script(ISO, WK, WK, CARROT, MEMOS) == lines)
    other = R.build_script((2026, 47), [dict(l, iso=(2026, 47)) for l in WK], WK, CARROT, MEMOS)
    check("주차가 다르면 진행 문구/게임이 달라짐", [t for _, _, t in other][:1] != texts[:1])

    # 8) 강사 데이터 없는 주 → AI 교정으로 Rewind, 형식 정상
    nl = R.build_script(ISO, WK, WK, {}, {})
    nt = [t for _, _, t in nl]
    check("강사 데이터 없음: 형식 정상", not format_problems(nl))
    check("강사 데이터 없음: 짧게 알리고 AI 교정으로 Rewind", any("No tutor notes" in t for t in nt) and any(t.startswith("Here's your AI coach's fix") for t in nt))
    check("강사 데이터 없음: 교정마다 한 줄 정리", sum(1 for _, lang, t in nl if lang == "ko" and t.startswith("한 줄 정리")) == sum(1 for t in nt if t.startswith("Here's your AI coach's fix")))
    check("강사 데이터 없음: ko 30% 이하", R.script_stats(nl)[2] <= 0.30)
    nn_, _, nr_ = R.script_stats(nl)
    print(f"   (synthetic W46 강사 없음: {nn_} lines, ko {nr_:.0%})")
    check(f"강사 데이터 없음: 최소 분량 {R.RADIO_MIN_LINES}줄 이상", nn_ >= R.RADIO_MIN_LINES)
    check("강사 데이터 없음: ko 10% 이상", nr_ >= 0.10)
    check("강사 데이터 없음: 같은 줄 되풀이 없음", not repeat_problems(nl))
    check("강사 데이터 없음: 'Tutor Rewind'라고 부르지 않음", not any("Tutor Rewind" in t for t in nt))
    check("AI 교정을 '강사가 고쳤다'고 하지 않음", not any(t.startswith("Your tutor rebuilt") for t in nt))
    empty = R.build_script(ISO, [dict(WK[0], pairs=[], vocab=[])], WK[:1], {}, {})
    check("교정이 하나도 없는 주도 대본 생성", empty and not format_problems(empty))
    check("교정이 하나도 없는 주: 되풀이로 채우지 않음", not repeat_problems(empty))

    # 8-1) 최소 분량 보충 코너 + 얇은 주(교정 < THIN_WEEK_ITEMS) 규칙
    thin_wk = [WK[0]]                                     # 수업 1회 · AI 교정 2개 · 강사 없음
    th = R.build_script(ISO, thin_wk, thin_wk, {}, {})
    tt = [t for _, _, t in th]
    check("얇은 주로 분류됨(교정 2개 < 기준)", is_thin(ISO, thin_wk, {}, {}))
    check("얇은 주: 형식 정상 · 되풀이로 채우지 않음", not format_problems(th) and not repeat_problems(th))
    check("얇은 주: 120줄 미만이면 짧은 회차 안내 줄", len(th) >= R.RADIO_MIN_LINES or R.SHORT_SHOW_LINE in tt)
    check("얇은 주: 쓸 수 있는 보충 코너는 다 넣음(게임·Repeat After Me·Pattern Practice·보너스 Culture)",
          any("It's game time" in t for t in tt) and any("Repeat After Me" in t for t in tt)
          and any("Pattern Practice" in t for t in tt) and any("one more Did You Know" in t for t in tt))
    check("120줄 이상이면 짧은 회차 안내 없음", R.SHORT_SHOW_LINE not in texts and R.SHORT_SHOW_LINE not in nt)
    check("보충 코너가 들어가도 학습자 문장은 실제 데이터만",
          all(re.split(r"[Yy]ou said: ", t, 1)[1].split(" Better: ")[0] in real_said
              for t in nt + tt if re.search(r"[Yy]ou said: ", t)))
    # 주차 회전(게임·Culture Corner·문구가 매주 바뀜) 12주 전부: 분량·되풀이·문법 용어·ko 비율·게임 수
    rot = []
    for w in range(40, 52):
        iso_w = (2026, w)
        wk_w = [dict(l, iso=iso_w) for l in WK]
        for cmap, mm in ((CARROT, MEMOS), ({}, {})):
            ls = R.build_script(iso_w, wk_w, wk_w, cmap, mm)
            nw, _, rw = R.script_stats(ls)
            tw = [t for _, _, t in ls]
            ng = sum(1 for g in ("Mistake Top 3 Countdown", "Spot the Mistake", "Real or Wrong", "Fix it in Three Seconds") if any(g in t for t in tw))
            if (nw < R.RADIO_MIN_LINES or nw > R.RADIO_MAX_LINES or not 0.10 <= rw <= 0.30 or repeat_problems(ls)
                    or jargon_hits(ls) or format_problems(ls) or not 1 <= ng <= 2):
                rot.append((w, bool(cmap), nw, round(rw, 2), repeat_problems(ls)[:1], jargon_hits(ls)[:1], ng))
    check("주차 회전 12주 × (강사 있음/없음): 120~200줄 · ko 10~30% · 되풀이·문법 용어 없음 · 게임 1~2개", not rot)
    if rot:
        print("   rotation problems:", rot[:3])

    # 9) 주제: AI 일일 피드백 Topic, 없으면 강사 메모
    mat = R.week_material(ISO, WK, CARROT, MEMOS)
    check("주제: 일일 Topic → 쉬운 구절", mat["topics"]["2026-11-11"] == "rubbish, recycling, and waste disposal in daily life")
    check("주제: 일일 페이지 없는 날은 강사 메모에서", mat["topics"].get("2026-11-10") == "building notices and fire drills")
    check("강사 교정은 ISO 주차 기준(일일 페이지 없는 날 포함)", any(it["date"] == "2026-11-10" for it in mat["tutor"]))

    # 10) 교정 분류(쉬운 이유 고르기)
    fam = lambda a, b: (R._diff(a, b) or {}).get("fam")
    check("분류: is + -ing", fam("He hold the step.", "He is standing on the stepladder.") == "be_ing")
    check("분류: is/are", fam("Are there any good news?", "Is there any good news?") == "is_are")
    check("분류: 지난 일", fam("I come back my office.", "I came back to my office.") == "past")
    check("분류: a/the", fam("It is same to Korea.", "It is the same as Korea.") == "article")
    check("분류: 단어 모양", fam("I'm so drowsiness.", "I'm so drowsy.") == "shape")
    check("분류: 일상 단어", fam("I changed the part that pours water.", "I changed my showerhead.") == "word")
    check("같은 문장은 교정 아님", R._diff("It is good.", "it is good") is None)
    check("TTS 다듬기: 강조 대문자·a/b·괄호", R._speakable("I will GO TO ULSAN after class (today)") == "I will go to Ulsan after class."
          and R._speakable("use/access the board") == "Use or access the board.")

    # 11) 페이지 렌더 → 플레이어/오디오가 같은 줄을 읽는다 + <pre id="radio-src" hidden> 그대로
    src = R._lines_to_src(lines)
    page = R.render(ISO, src, R.build_chat_prompts(ISO, WK, WK, CARROT), [], is_hub=True)
    check("<pre id=\"radio-src\" hidden> 태그 그대로", '<pre id="radio-src" hidden>' in page)
    try:
        import build_radio_audio as A
    except ImportError as e:   # requests 미설치 환경
        A = None
        print(f"   (build_radio_audio import 건너뜀: {e})")
    with tempfile.TemporaryDirectory() as td:
        fp = os.path.join(td, "radio-2026-W46.html")
        open(fp, "w", encoding="utf-8").write(page)
        got_src, got_wk = R._extract_src_and_week(fp)
        check("페이지에서 대본·주차 그대로 복원", got_src == src and got_wk == "2026-W46")
        # 브라우저 플레이어와 같은 규칙: 첫 '|'·둘째 '|' 로 나눈다
        js = [(ln[:ln.index("|")], ln[ln.index("|") + 1:ln.index("|", ln.index("|") + 1)], ln[ln.index("|", ln.index("|") + 1) + 1:])
              for ln in (x.strip() for x in got_src.split("\n")) if ln]
        check("플레이어 분해 = 원래 줄", js == lines)
        if A:
            wk_label, alines = A.parse_radio_html(fp)
            check("오디오 스크립트가 같은 줄을 읽음(2명·en/ko)", wk_label == "2026-W46" and alines == lines
                  and {s for s, _, _ in alines} <= set(A.SPEAKERS))

    # 12) 보존 정책: 같은 주 대본이 이미 있으면 그대로(루틴 Claude 대본 보호)
    with tempfile.TemporaryDirectory() as td:
        old_docs = R.DOCS
        R.DOCS = td
        try:
            hand = "민지|en|Hand-written show line.\n알렉스|ko|직접 쓴 줄."
            open(os.path.join(td, "radio.html"), "w", encoding="utf-8").write(R.render(ISO, hand, R.build_chat_prompts(ISO, WK, WK, CARROT), [], True))
            check("허브: 같은 주 대본은 보존", R.resolve_src(ISO, True, src) == hand)
            check("허브: 다른 주면 규칙기반", R.resolve_src((2026, 47), True, src) == src)
        finally:
            R.DOCS = old_docs

    # 13) 실제 데이터 전 주차(있으면): 형식·ko 비율·줄 수
    try:
        real = W.load_all()
        cm = W.load_carrot()
        memos = R.load_carrot_memos()
    except Exception as e:  # 데이터 없는 체크아웃
        real, cm, memos = [], {}, {}
        print(f"   (실데이터 건너뜀: {e})")
    if real:
        weeks = {}
        for l in real:
            weeks.setdefault(l["iso"], []).append(l)
        probs, short, reps, thin_short, sizes = [], [], [], [], {True: [], False: []}
        for iso, wk in weeks.items():
            cum = [l for l in real if l["iso"] <= iso]
            for cmap in (cm, {}):
                ls = R.build_script(iso, wk, cum, cmap, memos)
                nn, _, rr = R.script_stats(ls)
                sizes[bool(cmap)].append(nn)
                if format_problems(ls) or rr > 0.30 or nn > 200:
                    probs.append((W.week_label(iso), nn, round(rr, 2), bool(cmap)))
                if nn < R.RADIO_MIN_LINES:
                    lt = [t for _, _, t in ls]
                    if is_thin(iso, wk, cmap, memos) and (R.SHORT_SHOW_LINE in lt or any("notebook is a little empty" in t for t in lt)):
                        thin_short.append((W.week_label(iso), nn, bool(cmap)))
                    else:
                        short.append((W.week_label(iso), nn, bool(cmap)))
                if repeat_problems(ls):
                    reps.append((W.week_label(iso), bool(cmap), repeat_problems(ls)[:1]))
        print(f"   (실데이터 줄 수: 강사 있음 {min(sizes[True])}~{max(sizes[True])} · 강사 없음 {min(sizes[False])}~{max(sizes[False])}"
              f" · 얇은 주라 짧게 둔 경우 {thin_short})")
        check(f"실데이터 {len(weeks)}주 × (강사 있음/없음): 형식·ko≤30%·≤200줄", not probs)
        if probs:
            print("   problems:", probs[:5])
        check(f"실데이터 {len(weeks)}주 × (강사 있음/없음): {R.RADIO_MIN_LINES}줄 이상 (예외는 안내 줄 있는 얇은 주뿐)", not short)
        if short:
            print("   too short:", short[:5])
        check(f"실데이터 {len(weeks)}주 × (강사 있음/없음): 같은 줄 되풀이 없음", not reps)
        if reps:
            print("   repeats:", reps[:3])

    print(f"\n{'ALL PASS' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

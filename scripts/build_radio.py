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

CLI:  python3 scripts/build_radio.py                    # 전체 주차 생성(백필) + 허브
      python3 scripts/build_radio.py --preview 2026-W46  # 그 주 규칙기반 대본만 출력(파일 안 씀) + 줄 수·ko 비율
"""
import os, sys, html, datetime, re, glob, difflib
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
    """TTS 한 줄용: 개행 제거 + 구분자 | 치환 + 꺾쇠 무력화(플레이어가 말풍선을 innerHTML 로 그린다)."""
    return " ".join(str(s or "").split()).replace("|", "/").replace("<", "‹").replace(">", "›").strip()


def carrot_pairs_for_dates(carrot_map, dates):
    out = []
    for d in sorted(dates, reverse=True):
        for p in carrot_map.get(d, []):
            if p.get("original") or p.get("better"):
                out.append(p)
    return out


# ───────── 카테고리별 '왜 / 문화 / 팁' 인사이트 (규칙기반 심층화) ─────────
# 정규화 라벨(build_weekly_review.norm_grammar)에 substring 매칭(위에서부터 먼저 맞는 것).
# why_ko 는 한국어 음성으로 읽혀 '왜 그런지'를 학습자가 확실히 이해하게 한다.
# ⚠️ 2026-11-10: 문법책 용어(관사·전치사·3인칭 단수·조동사·동사원형·셀 수 있는 명사…) 없이 소리·그림·덩어리로 설명한다.
#    nick = 대본에서 카테고리 이름 대신 부르는 쉬운 별명 · nick_ko = 한국어 줄에서 부르는 별명.
#    group = 강사 교정·AI 교정·주간 순위를 한 바구니로 묶는 키 (Mistake Top 3 · Why It Happens 공용).
_INS_ARTICLE = {
    "group": "article", "nick": "the little a and the habit", "nick_ko": "a, the 같은 작은 말",
    "why_en": "Korean has no a, an, or the, so these tiny words feel optional. But in English they quietly tell the listener: is this any one, or the one we both already know?",
    "why_ko": "한국어에는 a, an, the 같은 말이 없어서 빼먹기 쉬워요. 영어에서는 이 작은 말이 '아무거나 하나'인지 '우리 둘 다 아는 바로 그거'인지 알려 줘요.",
    "culture_en": "Listen to native speakers tell a story. I saw a movie. The movie was long. First time, a. After that, the. They track what the listener already knows.",
    "tip_en": "Quick test: a brand-new thing gets a or an. A thing we both already know gets the.",
    "tip_ko": "처음 나오는 하나는 a, 서로 아는 그것은 the."}
_INS_PREP = {
    "group": "preposition", "nick": "the in, on, at picture", "nick_ko": "in, on, at 같은 작은 말 고르기",
    "why_en": "Small words like in, on, and at never match Korean one-to-one. The same Korean ending can become in, on, at, or to, depending on the picture in your head.",
    "why_ko": "in, on, at 같은 작은 말은 한국어와 하나씩 딱 안 맞아요. 같은 '에, 에서'도 머릿속 그림에 따라 in, on, at, to로 갈려요.",
    "culture_en": "English speakers see a tiny picture for each one. You are on the bus, because you can stand and walk on it. But you are in the car, because it's a small box around you.",
    "tip_en": "Picture it: a point gets at, a surface gets on, a box around you gets in.",
    "tip_ko": "점은 at, 표면은 on, 나를 둘러싼 상자는 in. 그림으로 떠올려요."}
_INS_WHO = {
    "group": "who", "nick": "the who-and-do habit", "nick_ko": "'누가' 빼먹기",
    "why_en": "Korean happily drops who did it, and sometimes even the action word, because the listener can guess. English almost always wants both: who, then what they do.",
    "why_ko": "한국어는 '누가'를 자주 빼도 다 알아들어요. 영어는 거의 항상 '누가 + 무엇을 한다'를 둘 다 말해요: (I) went there, It is good.",
    "culture_en": "That's why English even says it is raining. Nobody is doing the raining, but English still wants someone at the front of the sentence.",
    "tip_en": "Start every sentence with who, then the action: I went. It is. They said.",
    "tip_ko": "영어 문장은 '누가'로 시작해요: I went, It is."}
_INS_AGREE = {
    "group": "agreement", "nick": "the little s habit", "nick_ko": "끝소리 s",
    "why_en": "In Korean the action word never changes for he or she, and you often skip who did it. In English, you say who, and when it's he, she, or it, the action word gets a tiny s.",
    "why_ko": "한국어는 '그가'든 '그녀가'든 '간다'가 그대로고, 누가 했는지도 자주 빼요. 영어는 누가인지 꼭 말하고, 나·너가 아닌 '그 사람 하나'면 끝에 s를 붙여요: she works, it looks.",
    "culture_en": "That little s is tiny, but native ears expect it. When it's missing, people still understand you. It just sounds like a small bump in the road.",
    "tip_en": "He, she, it — add an s. She works. It looks. Say it like a reflex.",
    "tip_ko": "그 사람 하나, 그것 하나면 끝에 s: she works, it looks."}
_INS_HELPER = {
    "group": "verbform", "nick": "the do, did, have helper", "nick_ko": "do, did 같은 도우미 말",
    "why_en": "English loves little helper words in front, like do, did, and have. Once the helper carries the time, the main word just stays plain.",
    "why_ko": "영어는 do, did, have 같은 작은 도우미 말을 앞에 세워요. 도우미가 '언제'를 맡으면 뒤의 말은 그냥 사전 모양 그대로 두면 돼요: Did you go? (Did you went? ✗)",
    "culture_en": "Questions in English almost always start with a helper: do you, did you, can you. Korean just changes the end of the sentence, but English moves a helper to the front.",
    "tip_en": "Let the helper do the work: did you go, does it work, have you seen.",
    "tip_ko": "도우미 말이 때를 맡으면 뒤는 사전 모양 그대로: did you go."}
_INS_TIME = {
    "group": "time", "nick": "the time in the verb", "nick_ko": "때에 맞는 말 모양",
    "why_en": "Korean often shows time with words like yesterday or already, while English puts the time right inside the action word itself.",
    "why_ko": "한국어는 '어제, 벌써' 같은 말로 때를 알려 주지만, 영어는 말 자체의 모양을 바꿔서 때를 알려 줘요: go는 어제면 went.",
    "culture_en": "English ears hear time inside the word. If you say I go there yesterday, the word go and the word yesterday tell two different stories.",
    "tip_en": "If it's finished and past, let the word show it: go becomes went, eat becomes ate.",
    "tip_ko": "지난 일이면 말 모양부터 바꿔요: go는 went, call은 called."}
_INS_ING = {
    "group": "ing", "nick": "the -ing after little words", "nick_ko": "-ing 모양",
    "why_en": "After little words like at, in, about, and of, English wants the -ing shape: good at cooking, interested in learning. There's no Korean rule like this, so it just needs lots of hearing.",
    "why_ko": "at, in, about, of 같은 작은 말 뒤에는 -ing 모양이 와요: good at cooking, interested in learning. 한국어엔 없는 습관이라 덩어리로 많이 들어야 익숙해져요.",
    "culture_en": "Think of the -ing shape as turning an action into a thing you can hold: cooking, learning, running. Then little words like at and in can grab it.",
    "tip_en": "Learn it as one chunk: good at cooking, thinking about going, interested in learning.",
    "tip_ko": "at, in, about 뒤에는 -ing: good at cooking."}
_INS_MUCH = {
    "group": "determiner", "nick": "the much or many choice", "nick_ko": "much, many 고르기",
    "why_en": "Much, many, a few, a little — English picks a different word depending on whether you can count the thing one by one. Korean doesn't make you choose, so it's an easy place to wobble.",
    "why_ko": "much, many처럼 영어는 하나, 둘 셀 수 있는 거냐 아니냐에 따라 말을 바꿔요. 사과는 many apples, 물이나 시간은 much time. 한국어는 그 구분이 없어서 흔들리기 쉬워요.",
    "culture_en": "English speakers sort the world into things you count, like apples and chairs, and things you pour or measure, like water, time, and money.",
    "tip_en": "Can you count it, one, two, three? Use many. Can't count it, like water or time? Use much.",
    "tip_ko": "하나, 둘 셀 수 있으면 many, 못 세면 much."}
_INS_COMPARE = {
    "group": "compare", "nick": "the bigger-than pattern", "nick_ko": "비교할 때 -er",
    "why_en": "In Korean you just put one little word in front to mean more. English changes the word itself: hard becomes harder, big becomes bigger. Only long words use more, like more expensive.",
    "why_ko": "한국어는 '더'만 붙이면 되지만, 영어는 짧은 단어 끝에 -er을 붙여요: harder, bigger. 긴 단어만 more를 써요: more expensive.",
    "culture_en": "And never both at once. More harder sounds funny to native ears, a bit like saying very very twice.",
    "tip_en": "Short word? Add -er. Long word? Use more. Then add than: harder than, more expensive than.",
    "tip_ko": "짧은 단어는 -er, 긴 단어는 more. 둘을 같이 쓰지 않아요."}
_INS_ORDER = {
    "group": "order", "nick": "the word order flip", "nick_ko": "단어 순서",
    "why_en": "Korean puts the action at the very end. English puts it right after who: who, then do, then what. That's why the order can feel upside down.",
    "why_ko": "한국어는 '한다'가 맨 끝에 오지만, 영어는 '누가' 바로 다음에 와요: 누가, 한다, 무엇을.",
    "culture_en": "For questions, English flips the first two words: you are becomes are you. That flip is how native ears know a question is coming.",
    "tip_en": "Who, do, what. I ride a bike. She drinks coffee.",
    "tip_ko": "영어 순서는 누가, 한다, 무엇을."}
_INS_EXTRA = {
    "group": "extra", "nick": "the say-it-once habit", "nick_ko": "같은 말 두 번",
    "why_en": "When we think while we speak, extra words sneak in. In English, short and clean usually sounds more confident.",
    "why_ko": "생각하면서 말하다 보면 같은 말이 한 번 더 들어가요. 영어는 짧고 깔끔할수록 더 자신 있게 들려요.",
    "culture_en": "English speakers even have a saying for this: less is more.",
    "tip_en": "If two words mean the same thing, keep one.",
    "tip_ko": "같은 뜻의 말이 두 번 나오면 하나만 남겨요."}
_INS_SHAPE = {
    "group": "shape", "nick": "the right shape of the word", "nick_ko": "단어 모양",
    "why_en": "In English, one idea can wear different shapes: pain, painful, painfully. You picked the right idea. English just wants the shape that fits that spot in the sentence.",
    "why_ko": "영어 단어는 같은 뜻이라도 모양이 여러 개예요: pain, painful. 뜻은 맞게 골랐고, 문장 속 자리에 맞는 모양만 고르면 돼요.",
    "culture_en": "Native speakers learn these as sound families: drowsy and drowsiness, difficult and difficulty. Hearing both side by side helps them stick.",
    "tip_en": "After is or so, use the describing shape: so painful, so difficult, so drowsy.",
    "tip_ko": "is, so 뒤에는 꾸며 주는 모양: so difficult, so painful."}
_INS_WORD = {
    "group": "word", "nick": "the everyday word hunt", "nick_ko": "딱 맞는 일상 단어 찾기",
    "why_en": "When a word is missing, you describe it with a long phrase. That's actually a great survival skill. But English often has one short everyday word waiting for you.",
    "why_ko": "모르는 단어는 길게 풀어서 설명하게 되죠. 좋은 생존 기술이에요. 그런데 영어엔 그걸 한 단어로 말하는 일상 단어가 있는 경우가 많아요.",
    "culture_en": "Native speakers do this too. When they forget a word, they say the thingy, or the whatchamacallit. Asking what's it called is totally normal.",
    "tip_en": "When you describe something the long way, ask your tutor: what's the everyday word for this?",
    "tip_ko": "길게 설명했다면 '이거 영어로 뭐라고 해요?' 하고 물어보세요."}
INSIGHTS = [
    ("Article", _INS_ARTICLE),
    ("'The'", _INS_ARTICLE),
    ("Preposition", _INS_PREP),
    ("Missing", _INS_WHO),    # Missing Subjects / Verbs — 'Subject' 보다 먼저 (같은 글자가 들어 있어 잘못 매칭되지 않게)
    ("Subject", _INS_AGREE),  # Subject–Verb Agreement
    ("Need Help", _INS_ING),
    ("Phrasal", _INS_WORD),
    ("Verb Form", _INS_HELPER),
    ("Question", _INS_HELPER),
    ("Tense", _INS_TIME),
    ("Participle", _INS_TIME),
    ("Conditional", _INS_TIME),
    ("Gerund", _INS_ING),
    ("Determiner", _INS_MUCH),
    ("Countable", _INS_MUCH),
    ("Compar", _INS_COMPARE),
    ("Word Order", _INS_ORDER),
    ("Redundant", _INS_EXTRA),
    ("Adjective", _INS_SHAPE),
    ("Noun", _INS_SHAPE),
    ("Verb", _INS_HELPER),    # 'Verb' 단독 라벨 — 가장 마지막(다른 Verb 라벨이 먼저 잡히게)
]
GROUP_INSIGHT = {ins["group"]: ins for _, ins in INSIGHTS}
DEFAULT_INSIGHT = {
    "group": "", "nick": "", "nick_ko": "",
    "why_en": "Most repeated mistakes aren't about vocabulary — they're tiny habits from translating Korean word-for-word. The fix is noticing the pattern, which you're doing right now.",
    "why_ko": "반복되는 실수는 대부분 단어 문제가 아니라, 한국어를 그대로 직역하는 작은 습관에서 나와요. 해결책은 패턴을 알아채는 것 — 지금 하고 있는 그거예요.",
    "culture_en": "Even native speakers carry little speaking habits. The difference is that they notice them and smile.",
    "tip_en": "Pick one pattern a week and hunt for it. Awareness alone fixes half of it.",
    "tip_ko": "한 주에 패턴 하나만 골라서 사냥해요."}

# 흥미 코너: 어원·관용구·문화 대비 이야기(주차마다 회전 → 지루함 방지). (en, ko)
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
    ("Goodbye is a squeezed-down form of God be with ye, an old way to say take care. People said it faster and faster for hundreds of years, until it became goodbye.",
     "goodbye는 원래 'God be with ye', 신이 함께하길이라는 말을 줄인 거예요. 수백 년 동안 점점 빨리 말하다 보니 goodbye가 됐대요."),
    ("Why do we say hello on the phone? Thomas Edison pushed for hello. Alexander Graham Bell, who made the telephone, wanted people to answer with ahoy, like sailors!",
     "전화 받을 때 hello라고 하는 건 에디슨 덕분이래요. 전화를 만든 벨은 뱃사람처럼 ahoy라고 받자고 했대요."),
    ("The word robot comes from a Czech word, robota, which means hard, forced work. It first showed up in a 1920 play about factory-made workers.",
     "robot은 체코어 robota, '고된 노동'에서 온 말이에요. 1920년 연극에 처음 나왔어요."),
    ("In Korea, people say eye shopping. In English, it's window shopping: looking at shop windows without buying anything.",
     "한국에선 '아이쇼핑'이라고 하지만 영어로는 window shopping이에요. 진열창만 구경한다는 뜻이죠."),
    ("The word salary comes from the Latin word for salt. In ancient Rome, salt was so valuable that the word for it got tied to the money people earned.",
     "salary는 라틴어 '소금'에서 온 말이에요. 옛날 로마에선 소금이 그만큼 귀했대요."),
    ("The sandwich is named after the Earl of Sandwich, an English nobleman in the 1700s. The story goes that he wanted food he could eat with one hand while playing cards.",
     "sandwich는 1700년대 영국 샌드위치 백작 이름에서 왔어요. 카드 게임을 하면서 한 손으로 먹으려 했다는 이야기가 있어요."),
]

# 라디오 장치: 스테이션 ID·사인오프·카운트다운 대사 (주차 번호로 결정론적 회전)
JINGLES = [
    "You're tuned in to Joey FM, ninety-nine point one. English that sticks!",
    "This is Joey FM, ninety-nine point one, where your real mistakes turn into real English.",
    "Joey FM, ninety-nine point one. Your week, your words, your radio.",
]
SIGNOFFS = [
    "This has been Joey FM, ninety-nine point one. Keep talking, and see you next Friday!",
    "That's a wrap for Joey FM, ninety-nine point one. Same time next Friday!",
    "You've been listening to Joey FM, ninety-nine point one. Stay curious, and see you next Friday!",
]
QUIZ_BEATS = [
    "Can you hear what's off? Think for three seconds. Three, two, one.",
    "Hmm, something's a little off there. Can you fix it before Alex does? Three, two, one.",
    "Pause and try it yourself. What would you say instead? Three, two, one.",
]
REACTIONS = [
    "Oh, that sounds so much smoother. Alex, what changed?",
    "Small change, big difference. Why does that work better?",
    "Ahh, I can hear it now. So what's the secret?",
]
WEEKDAY_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKDAY_KO = ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일")
ORDINAL_KO = ("첫째", "둘째", "셋째", "넷째")
SENTENCE_GAMES = ("spot", "real", "fix3")   # Spot the Mistake · Real or Wrong? · Fix it in 3 seconds
GAME_TITLES = {"spot": "Spot the Mistake", "real": "Real or Wrong", "fix3": "Fix it in Three Seconds"}
GAME_RULES = {"spot": "I read a real sentence from your week. You find the slip before Alex tells you.",
              "real": "I read a sentence. Some are exactly what you said, some are the fixed version. You decide: real English, or wrong?",
              "fix3": "Alex reads one of your sentences, and you have three seconds to fix it out loud."}
# 문장 게임 카운트다운 — 문제마다 돌려 써서 같은 줄이 두 번 넘게 나오지 않게(한 게임 최대 6문제 = 변형 3개 × 2).
GAME_BEATS = {
    "spot": ("Spot it? Three, two, one.", "Can you hear the slip? Three, two, one.", "Where's the little bump? Three, two, one."),
    "real": ("Real, or wrong? Decide now. Three, two, one.", "Real English, or a slip? Three, two, one.",
             "Your call. Real or wrong? Three, two, one."),
    "fix3": ("Three, two, one!", "Quick, fix it! Three, two, one!", "Go! Three, two, one!"),
}
REAL_YES = ("Real! That's the natural version. On {d}, you first said it a different way.",
            "Real! That's the fixed one. On {d}, your first try sounded a little different.",
            "Real English! But on {d}, you said it another way first.")
SAME_LESSON = ("Still on {d}, same lesson. One more.", "Same {d} lesson, next sentence.", "One more from that {d} lesson.")

# ───────── 최소 분량(120줄) 보충 코너 / minimum-length fillers ─────────
# 스펙(radio_script_spec.md): 120~200줄. 기본 런다운이 120줄 미만이면 아래 우선순위로 '보충 코너'를 하나씩 끼워 넣는다
# (모두 그 주 실제 데이터 또는 고정 교재 문구 — 학습자 문장을 지어내지 않고, 같은 줄을 되풀이해 채우지 않는다):
#   1 Correction Clinic 추가분(아직 안 쓴 교정) → 2 게임 한 판 더 → 3 Repeat After Me(고친 덩어리 따라 하기)
#   → 4 2위 습관 짧은 심화 → 5 Joey's Line of the Week → 6 Topic Talk 단어 추가 → 7 Pattern Practice(1위 습관 예문)
#   → 8 보너스 Culture Corner.
# 쓸 수 있는 교정(강사+AI)이 THIN_WEEK_ITEMS 개 미만인 '얇은 주'는 다 넣어도 120줄이 안 될 수 있다 →
# 그대로 짧게 두고 대본에 SHORT_SHOW_LINE(짧은 회차 안내)을 넣는다. 120줄 미만인 대본은 얇은 주뿐이어야 한다(테스트로 확인).
RADIO_MIN_LINES = 120
RADIO_MAX_LINES = 200      # 오디오 무료 한도
THIN_WEEK_ITEMS = 3
SHORT_SHOW_LINE = "That's everything in the notebook this week, so today's show is a short one. Short, but every line counts."
# Pattern Practice: 1위 습관을 짧은 모범 문장 3개로 입에 붙이기 (고정 교재 문구 — 학습자 문장 아님, 문법 용어 없음).
PATTERN_DRILLS = {
    "article": ("I saw a movie. The movie was great.", "I have a car. The car is blue.", "Can you close the door, please?"),
    "preposition": ("I'm on the bus.", "I'm in the car.", "Let's meet at the station."),
    "who": ("I went there yesterday.", "It is cold today.", "They said it was fine."),
    "agreement": ("She works at a bank.", "It looks great.", "My son likes soccer."),
    "verbform": ("Did you go?", "Does it work?", "Have you seen it?"),
    "time": ("Yesterday I went to the store.", "Last week I called my mom.", "This morning I ate toast."),
    "ing": ("I'm good at cooking.", "I'm thinking about going.", "I'm interested in learning."),
    "determiner": ("How many apples?", "How much time?", "A few friends and a little money."),
    "compare": ("Seoul is bigger than Ulsan.", "This one is harder than that one.", "It's more expensive than before."),
    "order": ("I ride a bike.", "She drinks coffee.", "Are you ready?"),
    "extra": ("I went home.", "It was fun.", "We talked a lot."),
    "shape": ("It's so difficult.", "I'm so drowsy.", "It was so painful."),
    "word": ("What's it called?", "What's the word for this?", "How do you say this in English?"),
}


def _insight_for(top):
    for key, ins in INSIGHTS:
        if key.lower() in (top or "").lower():
            return ins
    return DEFAULT_INSIGHT


def _group_of_norm(norm):
    """AI 일일 피드백의 정규화 라벨 → 그룹 키 (모르는 라벨은 '')."""
    return _insight_for(norm).get("group", "")


def _weekday(d):
    """'2026-11-11' → ('Wednesday', '수요일')."""
    try:
        y, m, dd = map(int, str(d)[:10].split("-"))
        i = datetime.date(y, m, dd).weekday()
    except (ValueError, TypeError):
        return "that day", "그날"
    return WEEKDAY_EN[i], WEEKDAY_KO[i]


def _join_en(xs):
    xs = [x for x in xs if x]
    if len(xs) <= 1:
        return "".join(xs)
    return ", ".join(xs[:-1]) + (", and " if len(xs) > 2 else " and ") + xs[-1]


# ───────── 실제 문장 다듬기 (TTS 용) · 강사 메모 · 주제 ─────────
_KEEP_CAPS = {"I", "US", "UK", "USA", "USPS", "AI", "ID", "TV", "OK", "ATM", "CEO", "PC", "HR", "GPS",
              "SNS", "KTX", "DIY", "EU", "UN", "NYC", "LA", "SSN", "IRS", "ER", "ICU", "CPR", "PDF", "FAQ"}
_PROPER = {"korea", "korean", "koreans", "canada", "canadian", "japan", "japanese", "china", "chinese",
           "america", "american", "seoul", "busan", "ulsan", "airbnb", "asia", "asian", "english",
           "europe", "christmas", "chuseok"}


def _speakable(s):
    """강사/AI 원문 → 소리 내 읽기 좋은 한 문장. 첫 줄만 · 괄호 메모 제거 · 'Alternative:' 제거 ·
    a/b → a or b · 강조용 대문자 단어는 소문자로(약어는 유지). 단어를 지어내지 않는다."""
    s = str(s or "").strip()
    s = next((ln.strip() for ln in s.splitlines() if ln.strip()), "")
    s = re.sub(r"^\s*alternatives?\s*:\s*", "", s, flags=re.I)
    s = re.sub(r"\s*\([^)]*\)", "", s)
    s = s.replace("[", "").replace("]", "")
    s = re.sub(r"([A-Za-z])\s*/\s*([A-Za-z])", r"\1 or \2", s)
    words = []
    for w in s.split():
        core = re.sub(r"[^A-Za-z']", "", w)
        if len(core) >= 2 and core.isupper() and core not in _KEEP_CAPS:
            w = w.lower()
            if core.lower() in _PROPER:      # 강조 대문자를 내려도 지명·국가명은 대문자로 (ULSAN → Ulsan)
                w = w[:1].upper() + w[1:]
        words.append(w)
    s = " ".join(words)
    s = re.sub(r"\s+([,.!?;:])", r"\1", s).strip(" ,;:")
    if not s:
        return ""
    s = s[0].upper() + s[1:]
    if s[-1] not in ".?!":
        s += "."
    return s


def _toks(s):
    """문장 → (원래 단어들, 비교용 소문자 단어들). 구두점만 있는 조각은 버린다."""
    ws, ns = [], []
    for w in str(s).split():
        n = re.sub(r"[^a-z0-9']", "", w.lower().replace("’", "'"))
        if n:
            ws.append(w)
            ns.append(n)
    return ws, ns


def _span(words, lo, hi, cap=8):
    hi = min(hi, lo + cap)
    while hi < len(words) and hi - lo < cap and re.sub(r"[^a-z']", "", words[hi - 1].lower()) in _TINY:
        hi += 1                              # '… on the' 처럼 작은 말에서 끊기지 않게 한 단어 더
    t = " ".join(words[lo:hi])
    return t.strip(" ,;:").rstrip(".!?,;:")


_ART = {"a", "an", "the"}
_PREP = {"in", "on", "at", "to", "for", "with", "from", "of", "about", "by", "into", "onto", "as"}
_TINY = _ART | _PREP | {"my", "your", "his", "her", "our", "their"}
_BE = {"is", "are", "am", "was", "were", "be", "being", "been"}
_ISARE = {"is", "are", "am", "was", "were"}
_HELP = {"do", "does", "did", "don't", "doesn't", "didn't", "will", "won't", "can", "can't",
         "would", "could", "should"}
_PRON = {"i", "you", "he", "she", "it", "we", "they", "there", "this", "that"}
_OWN = {"my", "your", "his", "her", "our", "their", "this", "that", "these", "those", "some"}
_IRREG = {"go": "went", "come": "came", "take": "took", "make": "made", "have": "had", "get": "got",
          "see": "saw", "say": "said", "tell": "told", "eat": "ate", "buy": "bought", "think": "thought",
          "find": "found", "give": "gave", "know": "knew", "leave": "left", "feel": "felt", "meet": "met",
          "pay": "paid", "sleep": "slept", "fall": "fell", "run": "ran", "send": "sent", "spend": "spent",
          "bring": "brought", "begin": "began", "write": "wrote", "drive": "drove", "ride": "rode",
          "sit": "sat", "stand": "stood", "lose": "lost", "win": "won", "keep": "kept", "hear": "heard",
          "speak": "spoke", "wake": "woke", "forget": "forgot", "become": "became", "do": "did",
          "is": "was", "are": "were", "am": "was", "teach": "taught", "catch": "caught", "drink": "drank"}
_SOFT_FAMS = {"rephrase", "word"}   # '강사·AI가 같이 짚었다'고 말하기엔 너무 넓은 묶음


def _is_past(x, y):
    return bool(x) and (y in (x + "ed", x + "d", x + x[-1] + "ed")
                        or (x.endswith("y") and y == x[:-1] + "ied") or _IRREG.get(x) == y)


def _is_more(x, y):
    return bool(x) and (y in (x + "er", x + "r", x + x[-1] + "er") or (x.endswith("y") and y == x[:-1] + "ier"))


def _fam_of(ops, a_n, b_n, ratio):
    """비교 결과 → (세부 습관 fam, 틀린 단어, 고친 단어). 규칙기반 휴리스틱(결정론적)."""
    if ratio < 0.35:
        return "rephrase", "", ""
    pairs = []   # (틀린 단어, 고친 단어, 고친 문장 속 위치) — 나란히 바뀐 것만 (긴 문장 통째 교체에서 엉뚱한 짝 방지)
    for tag, i1, i2, j1, j2 in ops:
        if tag != "replace":
            continue
        A, B = a_n[i1:i2], b_n[j1:j2]
        if len(A) == len(B):
            pairs += [(x, y, j1 + k) for k, (x, y) in enumerate(zip(A, B))]
        elif min(len(A), len(B)) == 1 and max(len(A), len(B)) <= 3:
            pairs += [(x, y, j1 + kb) for x in A for kb, y in enumerate(B)]
        else:
            pairs += [(x, y, j1 + kb) for x in A for kb, y in enumerate(B)
                      if x != y and len(os.path.commonprefix([x, y])) >= max(3, min(len(x), len(y)) - 1)]
    for tag, i1, i2, j1, j2 in ops:          # 2) 지금 하는 중: is/are + -ing
        B = b_n[j1:j2]
        if not (set(a_n[i1:i2]) & _BE):
            for k, t in enumerate(B):
                nxt = b_n[j1 + k + 1] if j1 + k + 1 < len(b_n) else ""
                if t in _BE and nxt.endswith("ing"):
                    return "be_ing", "", t + " " + nxt
    for x, y, j in pairs:                    # 3) 지난 일 → 말 모양 (the recycled product 처럼 꾸미는 자리는 제외)
        if _is_past(x, y):
            if j and b_n[j - 1] in _ART | _OWN:
                return "shape", x, y
            return "past", x, y
    for x, y, _ in pairs:                    # 4) is ↔ are
        if x in _ISARE and y in _ISARE and x != y:
            return "is_are", x, y
    for x, y, _ in pairs:                    # 5) 끝소리 s
        if y in (x + "s", x + "es") or x == y + "s" or (x, y) in (("have", "has"), ("do", "does"), ("don't", "doesn't")):
            return "s_habit", x, y
    for tag, i1, i2, j1, j2 in ops:          # 6) 도우미 말(do/does/did/will/can)
        if set(b_n[j1:j2]) & _HELP and not set(a_n[i1:i2]) & _HELP:
            return "helper", "", next(t for t in b_n[j1:j2] if t in _HELP)
    for x, y, _ in pairs:                    # 7) 비교: -er
        if _is_more(x, y):
            return "compare", x, y
    if "than" in b_n and "than" not in a_n:
        return "compare", "", "than"
    for tag, i1, i2, j1, j2 in ops:          # 8) a / an / the
        A, B = set(a_n[i1:i2]), set(b_n[j1:j2])
        if (tag == "insert" and B <= _ART) or (tag == "delete" and A <= _ART) or (A and B and A <= _ART and B <= _ART):
            return "article", "", ""
    for tag, i1, i2, j1, j2 in ops:          # 9) in / on / at / to …
        A, B = set(a_n[i1:i2]), set(b_n[j1:j2])
        if (tag == "insert" and B <= _PREP) or (tag == "delete" and A <= _PREP) or (A and B and A <= _PREP and B <= _PREP):
            return "preposition", "", ""
    for tag, i1, i2, j1, j2 in ops:          # 10) 같은 뜻, 다른 모양(drowsiness → drowsy)
        if tag == "replace" and i2 - i1 == 1 and j2 - j1 == 1:
            x, y = a_n[i1], b_n[j1]
            p = len(os.path.commonprefix([x, y]))
            if p >= 4 or (p >= 3 and min(len(x), len(y)) >= 5):
                return "shape", x, y
    for tag, i1, i2, j1, j2 in ops:          # 11) '누가' 빼먹기
        if tag == "insert" and b_n[j1] in _PRON and (j1 == 0 or b_n[j1 - 1] in ("and", "but", "so", "because")):
            return "who", "", b_n[j1]
    for x, y, _ in pairs:                    # 12) -ing 모양
        if y.endswith("ing") and not x.endswith("ing") and y[:3] == x[:3]:
            return "ing", x, y
    if all(tag == "delete" for tag, *_ in ops):
        return "extra", "", ""               # 13) 군더더기 빼기
    if sorted(a_n) == sorted(b_n):
        return "order", "", ""               # 14) 순서만 바뀜
    return "word", "", ""                    # 15) 딱 맞는 일상 단어


# 세부 습관(fam) → 그룹 · 쉬운 이유(en/ko). {a}/{b}=바뀐 단어, {fix}=고친 덩어리.
FAMS = {
    "be_ing": ("verbform", "It's happening right now, so English puts is or are in front of the -ing word: {fix}.",
               "지금 하고 있는 일이면 -ing 앞에 is나 are를 꼭 붙여요."),
    "helper": ("verbform", "English wants a little helper word here, like do, does, or did: {fix}.",
               "영어는 do, does, did 같은 도우미 말을 앞에 세워요."),
    "past": ("time", "It already happened, so the word changes shape: {a} becomes {b}.",
             "이미 지난 일이라 말 모양이 바뀌어요."),
    "is_are": ("agreement", "Is goes with one thing, are goes with more than one. So here we say: {fix}.",
               "하나면 is, 여럿이면 are예요."),
    "s_habit": ("agreement", "Listen for the little s at the end: {b}, not {a}. Tiny sound, but native ears notice it.",
                "끝소리 s 하나 차이예요."),
    "compare": ("compare", "When you compare, short words just get -er, and then than: {fix}.",
                "비교할 땐 짧은 단어 끝에 -er을 붙여요."),
    "article": ("article", "One tiny word makes it sound natural: {fix}. English likes a little a, an, or the in front of things.",
                "작은 말 a, an, the 하나로 훨씬 자연스러워져요."),
    "preposition": ("preposition", "It's all about the little word in between: {fix}. Picture the scene, and the right little word follows.",
                    "in, on, at, to 같은 작은 말은 머릿속 그림으로 골라요."),
    "shape": ("shape", "Right idea, different shape: {b}, not {a}.",
              "뜻은 맞았고, 단어 모양만 달라요."),
    "who": ("who", "English almost always says who first: {fix}.",
            "영어는 '누가'를 꼭 먼저 말해요."),
    "ing": ("ing", "Here English wants the -ing shape: {fix}.",
            "여기선 -ing 모양이 와요."),
    "extra": ("extra", "Say it once and stop. Dropping the extra word makes it cleaner: {fix}.",
              "필요 없는 말 하나를 빼면 더 깔끔해요."),
    "order": ("order", "Same words, new order: {fix}. English lines them up as who, do, what.",
              "단어는 같고 순서만 바뀌어요."),
    "word": ("word", "Native speakers have one everyday chunk for this: {fix}.",
             "길게 설명하는 대신 원어민이 쓰는 딱 맞는 말이 있어요."),
    "rephrase": ("word", "Your tutor rebuilt the whole sentence the way people really say it. Learn it as one chunk.",
                 "문장을 통째로 원어민 문장으로 외워 두세요."),
}


def _widen(lo, hi, n, least=3):
    """바뀐 구간 [lo, hi) 에 앞뒤 한 단어씩 붙이고, 그래도 짧으면(빼기만 한 경우 등) 앞쪽부터 넓혀 최소 3단어."""
    lo, hi = max(0, lo - 1), min(n, hi + 1)
    while hi - lo < least and (lo > 0 or hi < n):
        if lo > 0:
            lo -= 1
        else:
            hi += 1
    return lo, hi


def _first_sentence_end(words):
    for k, w in enumerate(words):
        if w.endswith((".", "?", "!")) and k < len(words) - 1:
            return k + 1
    return len(words)


def _diff(said, fix):
    """두 문장 비교 → 바뀐 덩어리(wrong/fix chunk) + 습관 분류. 같으면 None."""
    a_w, a_n = _toks(said)
    b_w, b_n = _toks(fix)
    if not a_n or not b_n or a_n == b_n:
        return None
    sm = difflib.SequenceMatcher(None, a_n, b_n, autojunk=False)
    ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
    ratio = sm.ratio()
    fam, aw, bw = _fam_of(ops, a_n, b_n, ratio)
    if fam == "rephrase":
        wrong, fixc = _span(a_w, 0, _first_sentence_end(a_w)), _span(b_w, 0, _first_sentence_end(b_w))
    else:
        i1, i2, j1, j2 = ops[0][1], ops[-1][2], ops[0][3], ops[-1][4]
        if j2 - j1 > 6 or i2 - i1 > 6:       # 바뀐 곳이 넓으면 첫 변화만
            i1, i2, j1, j2 = ops[0][1], ops[0][2], ops[0][3], ops[0][4]
        lo_a, hi_a = _widen(i1, i2, len(a_w))
        lo_b, hi_b = _widen(j1, j2, len(b_w))
        wrong = _span(a_w, lo_a, hi_a)
        fixc = _span(b_w, lo_b, hi_b)
    return {"fam": fam, "a": aw, "b": bw, "wrong_chunk": wrong or _span(a_w, 0, len(a_w)),
            "fix_chunk": fixc or _span(b_w, 0, len(b_w))}


def _make_item(src, date, said_raw, fix_raw, idx, topic="", norm=""):
    """교정 한 쌍 → 대본 재료(dict). 발음·용어 낭독 연습·같은 문장은 None. 'Alternative' 는 kind='alt'."""
    said_raw, fix_raw = str(said_raw or ""), str(fix_raw or "")
    if not said_raw.strip() or not fix_raw.strip() or "pronounc" in (said_raw + fix_raw).lower():
        return None
    if re.match(r"^\s*[A-Za-z][A-Za-z' ]{1,25}:\s", said_raw):   # 'Tax deduction: …' 같은 용어 낭독
        return None
    # 발음 연습: 강사가 대문자로 강조한 단어가 한 글자만 다르게 고쳐짐(RIKE → LIKE) → 소리 교정이라 제외
    caps = [w.lower() for w in re.findall(r"[A-Za-z']+", said_raw) if len(w) >= 3 and w.isupper() and w not in _KEEP_CAPS]
    fwords = {w.lower() for w in re.findall(r"[A-Za-z']+", fix_raw)}
    if any(len(x) == len(y) and x != y and sum(c1 != c2 for c1, c2 in zip(x, y)) == 1 for x in caps for y in fwords):
        return None
    said, fix = _speakable(said_raw), _speakable(fix_raw)
    base = {"src": src, "date": date, "idx": idx, "said": said, "fix": fix, "topic": topic, "norm": norm}
    if re.match(r"^\s*alternatives?\s*:", fix_raw, re.I):
        return dict(base, kind="alt") if said and fix else None
    if len(said.split()) < 3 or len(fix.split()) < 2:
        return None
    d = _diff(said, fix)
    if not d:
        return None
    fam = d["fam"]
    return dict(base, kind="fix", fam=fam, group=FAMS[fam][0], **{k: d[k] for k in ("a", "b", "wrong_chunk", "fix_chunk")})


def _why_en(it):
    t = FAMS[it["fam"]][1]
    if ("{a}" in t and not it.get("a")) or ("{b}" in t and not it.get("b")):
        t = "Same idea, just the natural English habit on top: {fix}."
    if it.get("src") == "ai":               # AI 교정인데 '강사가 고쳤다'고 말하지 않게
        t = t.replace("Your tutor", "Your AI coach")
    return t.format(a=it.get("a", ""), b=it.get("b", ""), fix=it["fix_chunk"])


def _why_ko(it):
    return FAMS[it["fam"]][2]


def load_carrot_memos():
    """docs/carrot/*.json → {date: 강사 메모}. (W.load_carrot 은 교정쌍만 돌려주므로 메모는 여기서 읽는다)"""
    out = {}
    for f in sorted(glob.glob(os.path.join(DOCS, "carrot", "*.json"))):
        try:
            j = _json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for it in (j.get("data") or {}).get("list") or []:
            d, m = (it.get("createDate") or "").strip(), (it.get("memo") or "").strip()
            if d and m:
                out.setdefault(d, m)
    return out


_TOPIC_LEAD = re.compile(r"^(?:discussing|discussed|talking about|comparing|understanding|exploring|"
                         r"reviewing|describing|sharing|learning about|practicing|practising)\s+", re.I)


def _topic_phrase(topic):
    """'Discussing post office services and package delivery options.' → 'post office services and package
    delivery options'. 'Understanding Health Insurance — Deductibles…' → 'health insurance'."""
    t = " ".join(str(topic or "").split())
    if len(t) >= 88:                        # 일일 페이지 파서가 90자에서 자른 주제 → 잘린 끝 단어 버리고 쉼표/and 앞까지
        t = t.rsplit(" ", 1)[0]
        if ", " in t:
            t = t.rsplit(", ", 1)[0]
        elif " and " in t:
            t = t.rsplit(" and ", 1)[0]
    t = re.split(r"\s[—–-]\s|:\s|;\s", t)[0]
    t = re.sub(r"([A-Za-z])\s*/\s*([A-Za-z])", r"\1 or \2", t)
    t = _TOPIC_LEAD.sub("", t).strip(" .!?,")
    t = re.sub(r",?\s+(?:and|including|with)\s+(?:related|the related)\s+(?:vocabulary|terminology|terms|expressions)$", "", t, flags=re.I)
    t = re.sub(r"\s*\([^)]*\)", "", t)
    if len(t.split()) > 9:                  # 길면 쉼표 → and 앞에서 자르기
        t = re.split(r",\s", t)[0]
        if len(t.split()) > 9:
            t = re.split(r"\s(?:and|as well as|after|including)\s", t)[0]
    words = t.split()[:9]
    titled = sum(1 for w in words if w[:1].isupper()) >= max(2, len(words) // 2)
    out = []
    for i, w in enumerate(words):
        core = re.sub(r"[^A-Za-z]", "", w.split("'")[0])
        if core.isupper() and len(core) >= 2:
            out.append(w)
        elif core.lower() in _PROPER:
            out.append(w[:1].upper() + w[1:])
        elif titled or i == 0:
            out.append(w.lower())
        else:
            out.append(w)
    return " ".join(out).strip(" ,")


def _short_topic(t):
    """오프닝에서 주제 나열용 짧은 이름: 'building notices and politely …' → 'building notices'."""
    t1 = re.split(r",\s", t or "")[0]
    if len(t1.split()) > 4:
        t2 = re.split(r"\s(?:and|as well as|including)\s", t1)[0]
        if len(t2.split()) >= 2:
            t1 = t2
    return " ".join(t1.split()[:5])


def _memo_topic(memo):
    m = re.search(r"\b[Ww]e\s+(?:discussed|talked about|reviewed the topic of)\s+([^.!:\n]{4,120})", str(memo or ""))
    return _topic_phrase(m.group(1)) if m else ""


def week_material(wk_iso, wk, carrot_map, memos=None):
    """한 주의 대본 재료: 강사 교정(tutor)·강사 대안 표현(alts)·AI 교정(ai)·날짜별 주제(topics)·수업 날짜(days)."""
    topics = {}
    for l in wk:
        if l.get("topic") and l["date"] not in topics:
            topics[l["date"]] = _topic_phrase(l["topic"])
    tutor, alts = [], []
    # 주차(ISO) 기준으로 강사 교정을 모은다 — AI 일일 페이지가 없는 날의 강사 수업도 빠지지 않게.
    for d, ps in sorted(W.carrot_for_week(carrot_map, wk_iso)):
        if d not in topics:
            mt = _memo_topic((memos or {}).get(d, ""))
            if mt:
                topics[d] = mt
        for k, p in enumerate(ps):
            it = _make_item("tutor", d, p.get("original"), p.get("better"), k, topics.get(d, ""))
            if it:
                (alts if it["kind"] == "alt" else tutor).append(it)
    ai = []
    for l in wk:
        for k, p in enumerate(l.get("pairs") or []):
            it = _make_item("ai", l["date"], p.get("said"), p.get("natural"), k, topics.get(l["date"], ""),
                            l.get("grammar_norm", ""))
            if it and it["kind"] == "fix":
                ai.append(it)
    days = sorted({l["date"] for l in wk} | {d for d, _ in W.carrot_for_week(carrot_map, wk_iso)})
    return {"tutor": tutor, "alts": alts, "ai": ai, "topics": topics, "days": days}


def _ai_flags(wk, ai_items):
    """AI 코치가 이번 주 짚은 그룹 → 첫 날짜. (일일 피드백의 Category + 분류가 뚜렷한 AI 교정)"""
    out = {}
    for l in sorted(wk, key=lambda x: x["date"]):
        g = _group_of_norm(l.get("grammar_norm", ""))
        if g:
            out.setdefault(g, l["date"])
    for it in ai_items:
        if it["fam"] not in _SOFT_FAMS:
            out.setdefault(it["group"], it["date"])
    return out


def _week_rank(wk, tutor, ai, lessons):
    """이번 주 가장 많이 반복된 습관 순위 [(group, n)]. 일일 Category + 강사 교정 + 분류가 뚜렷한 AI 교정."""
    c = Counter()
    for l in wk:
        g = _group_of_norm(l.get("grammar_norm", ""))
        if g:
            c[g] += 1
    for it in tutor:
        if it["fam"] != "rephrase":
            c[it["group"]] += 1
    for it in ai:
        if it["fam"] not in _SOFT_FAMS:
            c[it["group"]] += 1
    cum = Counter(_group_of_norm(l.get("grammar_norm", "")) for l in lessons)
    return sorted(c.items(), key=lambda kv: (-kv[1], -cum.get(kv[0], 0), kv[0]))


def _pick_rewind(cands, flags, n):
    """Tutor Rewind 후보 고르기: AI도 짚은 습관 → 분명한 교정 → 적당한 길이 순, 날짜는 최대한 다르게."""
    def key(it):
        both = it["group"] in flags and it["fam"] not in _SOFT_FAMS
        nw = len(it["said"].split())
        return (0 if both else 1, 1 if it["fam"] == "rephrase" else 0, 0 if 4 <= nw <= 14 else 1, it["date"], it["idx"])
    ranked = sorted(cands, key=key)
    picked, dates = [], set()
    for it in ranked:
        if len(picked) < n and it["date"] not in dates:
            picked.append(it)
            dates.add(it["date"])
    for it in ranked:
        if len(picked) < n and it not in picked:
            picked.append(it)
    return sorted(picked, key=lambda it: (it["date"], it["idx"]))


def _uniq_items(xs):
    """같은 문장 쌍(대소문자 무시) 중복 제거 — 순서 유지. / drop repeated (said, fix) pairs, keep order."""
    out, seen = [], set()
    for it in xs:
        k = (it["said"].lower(), it["fix"].lower())
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def _tidy(lines):
    """최종 안전망: 바로 앞 줄과 똑같은 줄, 이미 두 번 나온 줄은 뺀다 (같은 말 되풀이로 분량 채우기 금지).
    Safety net: drop a line equal to the previous one, or one already used twice."""
    out, seen = [], Counter()
    for ln in lines:
        t = ln[2]
        if (out and out[-1][2] == t) or seen[t] >= 2:
            continue
        seen[t] += 1
        out.append(ln)
    return out


def _closeness(it):
    """틀린 문장과 고친 문장이 얼마나 비슷한지(0~1). 1에 가까울수록 '거의 다 맞은' 문장."""
    return difflib.SequenceMatcher(None, _toks(it["said"])[1], _toks(it["fix"])[1], autojunk=False).ratio()


def build_script(wk_iso, wk, lessons, carrot_map, memos=None):
    """규칙기반 '라디오쇼' 대본 → [(speaker, lang, text), ...]. (scripts/radio_script_spec.md 의 런다운)
    Station ID·콜드 오픈 → 오프닝 → Tutor Rewind(요일+수업 주제+퀴즈+한 줄 정리) → 게임 → Why It Happens →
    한국어 중간 정리 → Correction Clinic → Culture Corner → Topic Talk → 한국어 3줄 요약 → 미션·사인오프.
    학습자 문장은 전부 실제 데이터(강사 JSON·일일 피드백)에서만 가져오고, 게임/문구는 주차 번호로 회전한다.
    기본 런다운이 RADIO_MIN_LINES(120) 미만이면 보충 코너를 우선순위대로 제자리(슬롯)에 끼워 120줄 이상으로 맞춘다
    (위 '최소 분량' 주석 참고). 얇은 주(교정 < THIN_WEEK_ITEMS)는 짧게 두고 SHORT_SHOW_LINE 으로 알린다.
    lessons = 그 주말까지 누적. (금요일 루틴의 Claude가 허브 #radio-src 를 더 깊은 담화로 교체)"""
    wnum = wk_iso[1] if isinstance(wk_iso, tuple) else 0
    mat = week_material(wk_iso, wk, carrot_map, memos)
    topics, tutor, ai, alts = mat["topics"], mat["tutor"], mat["ai"], mat["alts"]
    vocab = [(l["date"], v) for l in wk for v in (l.get("vocab") or []) if v.get("word")]
    flags = _ai_flags(wk, ai)
    rank = _week_rank(wk, tutor, ai, lessons)
    if not rank:
        cum = [(g, n) for g, n in Counter(_group_of_norm(l.get("grammar_norm", "")) for l in lessons).most_common() if g]
        rank = cum[:1]
    g1 = rank[0][0] if rank else ""
    g2 = rank[1][0] if len(rank) > 1 else ""
    ins = GROUP_INSIGHT.get(g1, DEFAULT_INSIGHT)
    nick1 = ins["nick"] or "your number one habit"
    nick2 = GROUP_INSIGHT[g2]["nick"] if g2 in GROUP_INSIGHT else ""
    fun_en, fun_ko = FUN_FACTS[wnum % len(FUN_FACTS)]

    L = []          # 기본 런다운 / core rundown
    buf = [L]       # add() 가 쓰는 곳(보충 코너는 따로 모았다가 슬롯에 끼운다)
    slots = {}      # 보충 코너를 끼울 자리: 이름 → L 의 위치

    def add(s, lang, t):
        t = _clean1(t)
        if t:
            buf[-1].append((s, lang, t))

    def capture(fn):
        out = []
        buf.append(out)
        try:
            ok = fn()
        finally:
            buf.pop()
        return [] if ok is False else out

    def day_en(d):
        return _weekday(d)[0]

    def day_ko(d):
        return _weekday(d)[1]

    def topic_of(d):
        return topics.get(d, "")

    used = []

    def mark(it):
        if it not in used:
            used.append(it)

    def unused(xs):
        return [x for x in xs if x not in used]

    def pool_key(it):
        return (len(it["said"].split()) > 16, it["src"] != "tutor", it["date"], it["idx"])

    rewind_src = "tutor" if tutor else "ai"
    rewind = _pick_rewind(tutor, flags, 4) if tutor else _pick_rewind(ai, flags, 3)
    for it in rewind:
        mark(it)

    # 1) Station ID + 콜드 오픈 — 실제 교정 하나로 '그때 그 문장' 궁금증 만들기
    add("민지", "en", JINGLES[wnum % len(JINGLES)])
    if rewind:
        t0 = rewind[0]
        who = "your tutor" if rewind_src == "tutor" else "your AI coach"
        where = f", while you were talking about {topic_of(t0['date'])}" if topic_of(t0["date"]) else ""
        add("알렉스", "en", f"This week {who} caught one sentence you said on {day_en(t0['date'])}{where}. Do you remember it? Stay tuned, it's coming up first.")
    add("민지", "en", "Hello, hello! I'm Minji, your host.")
    add("알렉스", "en", f"And I'm Alex, your English coach. Welcome to week {wnum}.")

    # 2) 오프닝 토크 — 이번 주 수업 요일·주제
    days = mat["days"]
    if days:
        dn = [day_en(d) for d in days]
        dn = list(OrderedDict.fromkeys(dn))
        when = "every day from Monday to Friday" if dn == list(WEEKDAY_EN[:5]) else "on " + _join_en(dn)
        add("민지", "en", f"So, this week you had class {when}.")
    tps = list(OrderedDict.fromkeys(_short_topic(t) for t in (topic_of(d) for d in days) if t))[:4]
    if tps:
        add("알렉스", "en", f"And the topics were real life: {_join_en(tps)}.")
    add("민지", "en", "Real situations, real sentences. Today we don't just list mistakes, we rewind and remember them.")

    # 3) Tutor Rewind (그때 그 수업) — 메인 코너
    if rewind_src == "tutor":
        add("알렉스", "en", "Let's start with our main segment, Tutor Rewind. These sentences came straight from your live lessons.")
    else:
        add("알렉스", "en", "Let's start with Rewind. No tutor notes came in for this week, so today we replay what your AI coach caught.")
    add("민지", "en", "I love this part. Let's go back in time.")
    told = set()
    run = 0
    for k, it in enumerate(rewind):
        d = it["date"]
        if k and rewind[k - 1]["date"] == d:
            scene = SAME_LESSON[run % len(SAME_LESSON)].format(d=day_en(d))
            run += 1
        elif topic_of(d):
            scene, run = f"Rewind to {day_en(d)}. You were talking about {topic_of(d)}.", 0
        else:
            scene, run = f"Rewind to {day_en(d)}, in your lesson.", 0
        add("민지", "en", scene)
        add("알렉스", "en", f"And at one point you said: {it['said']}")
        add("민지", "en", QUIZ_BEATS[(wnum + k) % len(QUIZ_BEATS)])
        coach = "Here's your tutor's fix" if it["src"] == "tutor" else "Here's your AI coach's fix"
        add("알렉스", "en", f"{coach}: {it['fix']}")
        add("민지", "en", REACTIONS[(wnum + k) % len(REACTIONS)])
        add("알렉스", "en", _why_en(it))
        ch = it["fix_chunk"]
        if len(ch.split()) >= 5 or ch.lower() == it["fix"].lower().rstrip(".!?"):
            add("알렉스", "en", f"Say it with me, nice and slow. {it['fix']} One more time. {it['fix']}")
        else:
            add("알렉스", "en", f"Say it with me. {ch}. {ch}. {it['fix']}")
        if it["src"] == "tutor" and it["group"] in flags and it["fam"] not in _SOFT_FAMS:
            g_nick = GROUP_INSIGHT.get(it["group"], DEFAULT_INSIGHT)["nick"] or "this habit"
            if it["group"] not in told:
                add("민지", "en", f"And here's the thing: your AI coach flagged {g_nick} on {day_en(flags[it['group']])} too. When your tutor and your AI coach both catch it, that's a real priority.")
            else:
                add("민지", "en", f"There it is again, {g_nick}. Tutor and AI coach agree on this one.")
            told.add(it["group"])
        add("민지", "ko", f"한 줄 정리: {day_ko(d)}에 '{it['wrong_chunk']}'라고 했는데, '{ch}'라고 하면 자연스러워요. {_why_ko(it)}")
    slots["rewind"] = len(L)
    if not rewind:
        add("알렉스", "en", "This week the notebook is a little empty, so we'll keep it short and sweet.")
    add("민지", "en", f"Coming up: game time, and then we dig into why {nick1} keeps coming back. Stay with us.")

    # 4) 게임 — 주차 번호로 회전 (Mistake Top 3 + 문장 게임 1개)
    by_group = {}
    for it in tutor + ai:
        by_group.setdefault(it["group"], []).append(it)
    pool = sorted(unused(tutor) + unused(ai), key=pool_key)
    gamed = []                                   # 문장 게임에 이미 낸 문제(한 게임에서 같은 문장 두 번 안 냄)
    played = {"top3": False, "kind": "", "n": 0}

    def game_top3():
        top = [(g, n) for g, n in rank if g in GROUP_INSIGHT][:3]
        if len(top) < 3:
            return False
        add("민지", "en", "And now, chart-show time. It's the Mistake Top 3 Countdown! The week's most repeated slips, from number three up to number one.")
        for pos, (g, n) in reversed(list(enumerate(top, 1))):
            gi = GROUP_INSIGHT[g]
            catches = f"{n} catch" if n == 1 else f"{n} catches"
            if pos == 1:
                add("민지", "en", "And now, drumroll please. Ba-dum, ba-dum, ba-dum.")
                add("알렉스", "en", f"Your number one slip of the week, with {catches}: {gi['nick']}!")
            else:
                add("알렉스", "en", f"At number {'three' if pos == 3 else 'two'}, with {catches}: {gi['nick']}.")
            ex = sorted(unused(by_group.get(g, [])) or by_group.get(g, []), key=lambda e: len(e["said"].split()))[:1]
            if ex:
                e = ex[0]
                mark(e)
                add("민지", "en", f"Like on {day_en(e['date'])}, when you said: {e['said']} Better: {e['fix']}")
            elif pos != 1:
                add("민지", "en", "Moving up the chart.")
            if pos == 1:
                add("민지", "ko", f"이번 주 1위는 {gi['nick_ko']}예요. {gi['tip_ko']}")
            else:
                add("민지", "ko", f"{pos}위, {gi['nick_ko']}. {gi['tip_ko']}")
        played["top3"] = True
        return True

    def play_items(kind, items, start):
        """문장 게임 문제들. 번호(start~)로 카운트다운 변형을 돌린다."""
        for k, it in enumerate(items, start):
            mark(it)
            gamed.append(it)
            beat = GAME_BEATS[kind][(k - 1) % len(GAME_BEATS[kind])]
            memo = f"정답 메모: '{it['wrong_chunk']}' 말고 '{it['fix_chunk']}'."
            if kind == "spot":
                add("민지", "en", f"Number {k}. {it['said']}")
                add("알렉스", "en", beat)
                add("알렉스", "en", f"Answer: {it['fix']}")
                add("민지", "ko", memo)
            elif kind == "real":
                show_real = (k + wnum) % 2 == 0
                add("민지", "en", f"Number {k}. {it['fix'] if show_real else it['said']}")
                add("알렉스", "en", beat)
                if show_real:
                    add("알렉스", "en", REAL_YES[(k - 1) % len(REAL_YES)].format(d=day_en(it["date"])))
                    add("민지", "ko", f"이건 맞는 문장이에요. 원래는 '{it['wrong_chunk']}'라고 했었죠.")
                else:
                    add("알렉스", "en", f"Wrong! The natural way is: {it['fix']}")
                    add("민지", "ko", memo)
            else:
                add("알렉스", "en", f"Fix this in three seconds: {it['said']}")
                add("민지", "en", beat)
                add("알렉스", "en", it["fix"])
                add("민지", "ko", memo)

    def game_sentences(kind):
        items = [it for it in pool if it not in used][:3]
        if len(items) < 2:
            return False
        add("민지", "en", f"It's game time! This one is called {GAME_TITLES[kind]}. {GAME_RULES[kind]}")
        play_items(kind, items, 1)
        add("알렉스", "en", "How many did you get? Even one is a win.")
        played["kind"], played["n"] = kind, len(items)
        return True

    sent = SENTENCE_GAMES[wnum % len(SENTENCE_GAMES)]
    order = (game_top3, lambda: game_sentences(sent)) if wnum % 2 == 0 else (lambda: game_sentences(sent), game_top3)
    for g in order:
        g()
    slots["game"] = len(L)

    # 5) Why It Happens — 이번 주 1위 습관 심화
    add("민지", "en", f"Now, Why It Happens. This week's number one habit is {nick1}. Alex, why does it keep coming back?")
    add("알렉스", "en", "Great question. " + ins["why_en"])
    add("민지", "ko", ins["why_ko"])
    add("알렉스", "en", ins["culture_en"])
    exs = sorted(unused(by_group.get(g1, [])), key=lambda e: (e["src"] != "tutor", len(e["said"].split())))[:2]
    for e in exs:
        mark(e)
        add("민지", "en", f"Here's one from {day_en(e['date'])}. You said: {e['said']}")
        add("알렉스", "en", f"And the natural version: {e['fix']}")
    if not exs:
        cb = [e for e in rewind if e["group"] == g1][:1]
        for e in cb:
            corner = "the Tutor Rewind" if rewind_src == "tutor" else "the Rewind"
            add("민지", "en", f"Remember {day_en(e['date'])}'s sentence from {corner}? {e['fix']} Same habit.")
    add("알렉스", "en", "Rule of thumb: " + ins["tip_en"])
    slots["why"] = len(L)

    # 6) 한국어 중간 정리 — 지금까지 고친 것
    recap = rewind[:3]
    if recap:
        add("민지", "en", "Okay, we're halfway through the show. Quick check-in in Korean, so nothing slips away.")
        for k, it in enumerate(recap):
            add("민지", "ko", f"중간 정리 {ORDINAL_KO[k]}, {day_ko(it['date'])} 수업: '{it['wrong_chunk']}' 말고 '{it['fix_chunk']}'.")
        if ins.get("nick_ko"):
            add("민지", "ko", f"그리고 이번 주 1위 습관은 {ins['nick_ko']}였어요.")

    # 7) Correction Clinic — 남은 교정 빠르게 (강사 먼저), 2개마다 한국어 메모
    def clinic_item(it, memo):
        mark(it)
        lead = f"From your tutor on {day_en(it['date'])}" if it["src"] == "tutor" else "You said"
        add("알렉스", "en", f"{lead}: {it['said']}")
        add("민지", "en", f"Better: {it['fix']}")
        if memo:
            add("민지", "ko", f"짧게 메모: '{it['wrong_chunk']}' 말고 '{it['fix_chunk']}'. {_why_ko(it)}")

    clinic = (unused(tutor)[:3] + unused(ai))[:6]
    if clinic:
        add("알렉스", "en", "Time for the Correction Clinic. Quick-fire, and repeat after us if you can.")
        for k, it in enumerate(clinic, 1):
            clinic_item(it, it["src"] == "tutor" or k % 2 == 0 or k == len(clinic))
    slots["clinic"] = len(L)

    # 8) Culture Corner / Did You Know — 흥미 이야기(회전)
    add("민지", "en", "Let's take a little break from corrections. It's Culture Corner. Did you know?")
    add("알렉스", "en", fun_en)
    add("민지", "ko", fun_ko)
    slots["culture"] = len(L)

    # 9) Topic Talk — 이번 주 주제 단어를 실제 문장과 함께
    seen, words = set(), []
    real = [it["fix"] for it in tutor + ai]
    for d, v in vocab:
        w = v["word"].strip()
        if w.lower() in seen:
            continue
        seen.add(w.lower())
        sent_hit = next((s for s in real if re.search(r"\b" + re.escape(w.lower()) + r"\b", s.lower())), "")
        words.append((0 if sent_hit else 1, d, w, v.get("meaning", ""), sent_hit))
    ranked_words = sorted(words, key=lambda x: (x[0], x[1]))
    words = sorted(ranked_words[:4], key=lambda x: x[1])
    more_words = sorted(ranked_words[4:8], key=lambda x: x[1])   # 보충 코너(Topic Talk 추가분)용

    def word_lines(ws, ko_lead):
        for _, d, w, meaning, s in ws:
            tp = topic_of(d)
            add("민지", "en", f"From {day_en(d)}'s lesson" + (f" on {tp}" if tp else "") + f": {w}.")
            if s:
                add("알렉스", "en", f"Here it is in a sentence from this week's corrections: {s}")
            else:
                add("알렉스", "en", f"{w}. Say it with me: {w}. Try it in one sentence today.")
        ms = []
        for _, _, w, meaning, _ in ws:
            m = re.split(r"[,(※/;]", str(meaning or ""))[0].strip()
            if m:
                ms.append(f"{w}, {m}")
        if ms:
            add("민지", "ko", ko_lead + ". ".join(ms) + ".")

    if words or alts:
        add("알렉스", "en", "Next up, Topic Talk. A few words from this week's lessons that you can use right away.")
    if words:
        word_lines(words, "뜻 정리할게요. ")
    if alts:
        a = alts[0]
        add("알렉스", "en", f"Bonus tip from your tutor on {day_en(a['date'])}. Instead of {a['said']} you can also say: {a['fix']}")
    slots["topic"] = len(L)

    # 10) 한국어 3줄 요약 — 오늘 꼭 기억할 세 가지
    keep3 = (rewind + [it for it in used if it not in rewind])[:2]
    add("알렉스", "en", "Before we go, here's today's three-line summary in Korean.")
    for k, it in enumerate(keep3):
        add("민지", "ko", f"{('하나', '둘')[k]}, '{it['wrong_chunk']}' 말고 '{it['fix_chunk']}'. {_why_ko(it)}")
    label3 = ("하나", "둘", "셋")[len(keep3)]
    if ins.get("nick_ko"):
        add("민지", "ko", f"{label3}, 이번 주 1위 습관 {ins['nick_ko']}. {ins['tip_ko']}")
    else:
        add("민지", "ko", f"{label3}, {ins['tip_ko']}")

    # 11) 미션 + 사인오프
    avg, cum_avg = W.avg_score(wk), W.avg_score(lessons)
    if avg:
        trend = "climbing" if avg >= cum_avg + 0.3 else ("taking a little breather" if avg <= cum_avg - 0.3 else "nice and steady")
        add("알렉스", "en", f"Quick check on the numbers. Your fluency average this week is {avg:.1f} out of ten, and it's {trend}.")
    mission = f"Your mission for next week: hunt for {nick1} every time you speak"
    if nick2:
        mission += f", and keep half an eye on {nick2}"
    add("민지", "en", mission + ". Awareness first, perfection later.")
    if ins.get("nick_ko"):
        m_ko = f"다음 주 미션: {ins['nick_ko']} 잡기"
        if g2 in GROUP_INSIGHT:
            m_ko += f", 그리고 {GROUP_INSIGHT[g2]['nick_ko']}도 살짝 신경 쓰기"
        add("민지", "ko", m_ko + ".")
    add("알렉스", "en", "Thanks for spending this time with us. Mistakes are just English habits waiting to click.")
    add("민지", "en", SIGNOFFS[wnum % len(SIGNOFFS)])
    add("알렉스", "en", "Bye, Joey! Keep talking!")

    # ───── 12) 최소 분량 보충 코너 (120줄 미만일 때만, 우선순위대로) ─────
    def f_clinic_more():
        """Correction Clinic 추가분 — 아직 안 쓴 실제 교정(강사 먼저). 2개마다 ko 메모."""
        more = _uniq_items(sorted(unused(tutor) + unused(ai), key=pool_key))[:6]
        if not more:
            return False
        add("알렉스", "en", "A few more from this week. Keep going, you're doing great." if len(more) > 1
            else "One more from this week. Keep going.")
        for k, it in enumerate(more, 1):
            clinic_item(it, k % 2 == 0 or k == len(more))

    def f_game2():
        """게임 한 판 더: 게임이 둘 다 나왔으면 같은 문장 게임 2라운드, 하나뿐이면 다른 문장 게임(회전),
        하나도 없었으면 이번 주 문장 게임. 안 쓴 교정 먼저, 모자라면 앞에서 들은 문장 복습."""
        if played["kind"] and played["top3"]:
            kind, again = played["kind"], True
        elif played["kind"]:
            kind, again = SENTENCE_GAMES[(SENTENCE_GAMES.index(played["kind"]) + 1) % len(SENTENCE_GAMES)], False
        else:
            kind, again = sent, False
        fresh = sorted(unused(tutor) + unused(ai), key=pool_key)
        items = [it for it in _uniq_items(fresh + rewind + used) if it not in gamed][:3]
        if len(items) < 2:
            return False
        replay = any(it in used for it in items)
        if again:
            add("민지", "en", f"Bonus round! It's {GAME_TITLES[kind]}, round two. Same rules, new numbers.")
        else:
            add("민지", "en", f"It's game time! This one is called {GAME_TITLES[kind]}. {GAME_RULES[kind]}")
        if replay:
            add("알렉스", "en", "Some of these you already heard today. Let's see if they stuck.")
        play_items(kind, items, played["n"] + 1 if again else 1)
        if again:
            add("알렉스", "en", "Round two, done. Hearing a fix again and again is exactly how it sticks.")
        elif played["kind"]:
            add("알렉스", "en", "That's game two. Every answer you said out loud counts.")
        else:
            add("알렉스", "en", "How many did you get? Even one is a win.")

    def f_drill():
        """Repeat After Me — 이번 주 고친 덩어리를 알렉스가 말하고 민지(=청취자)가 따라 한다."""
        items, keys = [], set()
        for it in rewind + used:
            key = it["fix_chunk"].lower()
            if key not in keys and len(it["fix_chunk"].split()) >= 2:
                keys.add(key)
                items.append(it)
        items = items[:5]
        if len(items) < 2:
            return False
        add("민지", "en", "Now, a quick Repeat After Me drill. Alex says each fixed chunk from this week. I copy him, and you copy too.")
        for k, it in enumerate(items, 1):
            add("알렉스", "en", f"Chunk {k}, from {day_en(it['date'])}: {it['fix_chunk']}. Your turn.")
            fc = it["fix_chunk"]
            add("민지", "en", f"{fc[:1].upper() + fc[1:]}. {it['fix']}")
            if k % 2 == 0 or k == len(items):
                pair = items[k - 2:k] if k % 2 == 0 else items[k - 1:k]
                add("민지", "ko", "따라 하기 메모: " + ", ".join(f"'{p['wrong_chunk']}' 대신 '{p['fix_chunk']}'" for p in pair)
                    + ". 덩어리째 입에 붙여요.")
        add("알렉스", "en", "Great job. Say those chunks out loud once more on your way to work tomorrow.")

    def f_why2():
        """2위 습관 짧은 심화 — 왜(en/ko) + 실제 예문 1개 + rule of thumb."""
        if g2 not in GROUP_INSIGHT or g2 == g1:
            return False
        i2 = GROUP_INSIGHT[g2]
        add("민지", "en", f"Before we move on, a quick look at habit number two: {i2['nick']}. Alex, what's the story there?")
        add("알렉스", "en", i2["why_en"])
        add("민지", "ko", i2["why_ko"])
        ex = sorted(by_group.get(g2, []), key=lambda e: (e in used, e["src"] != "tutor", len(e["said"].split()), e["date"]))[:1]
        for e in ex:
            if e in used:                     # 이미 들은 문장이면 통째로 다시 읽지 않고 짧게 콜백
                add("알렉스", "en", f"Remember {day_en(e['date'])}'s sentence? {e['fix']} That's this habit, fixed.")
            else:
                mark(e)
                add("알렉스", "en", f"Here's a real one from {day_en(e['date'])}. You said: {e['said']} Better: {e['fix']}")
        add("알렉스", "en", "Rule of thumb for this one: " + i2["tip_en"])

    def f_line():
        """Joey's Line of the Week — 거의 다 맞았던 실제 문장 하나(작은 차이로 고쳐진 것)를 다시 들려준다."""
        cands = [it for it in _uniq_items(tutor + ai)
                 if it["fam"] != "rephrase" and 4 <= len(it["said"].split()) <= 16 and _closeness(it) >= 0.6]
        if not cands:
            return False
        it = sorted(cands, key=lambda e: (e in rewind, -round(_closeness(e), 2), e["src"] != "tutor", e["date"], e["idx"]))[0]
        mark(it)
        tp = topic_of(it["date"])
        add("민지", "en", "And now, a listener favourite. It's Joey's Line of the Week!")
        add("알렉스", "en", f"This one is from {day_en(it['date'])}" + (f", when you were talking about {tp}" if tp else "")
            + f". You said: {it['said']}")
        add("민지", "en", "Ooh, so close. Just one small step away from perfect.")
        add("알렉스", "en", f"Exactly. Here's the polished version: {it['fix']} That's your line of the week. Use it again before next Friday.")
        add("민지", "ko", f"이번 주의 한 문장: '{it['fix_chunk']}'. 거의 다 맞았어요, 이 덩어리만 챙겨요.")

    def f_topic():
        """Topic Talk 추가분 — 기본 4개 다음 단어(최대 4개 더)."""
        if not more_words:
            return False
        n = len(more_words)
        lead = "One more word" if n == 1 else f"{('Two', 'Three', 'Four')[n - 2]} more words"
        add("알렉스", "en", f"{lead} from this week's lessons, because they're too useful to skip.")
        word_lines(more_words, "추가 단어 뜻이에요. ")

    def f_pattern():
        """Pattern Practice — 1위 습관을 짧은 모범 문장 3개로(고정 교재 문구)."""
        dr = PATTERN_DRILLS.get(g1)
        if not dr:
            return False
        add("민지", "en", f"Let's lock in that rule of thumb with a quick Pattern Practice for {nick1}. Three short sentences. Say each one after Alex.")
        for k, c in enumerate(dr):
            add("알렉스", "en", f"{('One', 'Two', 'Three')[k]}. {c} Again. {c}")
        add("민지", "ko", f"패턴 연습 정리: {ins['tip_ko']}")
        add("알렉스", "en", "Short and natural. Say them out loud a few times, and the pattern starts to feel automatic.")

    def f_culture():
        """보너스 Culture Corner — 기본 이야기와 다른 FUN_FACTS 하나(주차로 회전)."""
        fe, fk = FUN_FACTS[(wnum + len(FUN_FACTS) // 2) % len(FUN_FACTS)]
        if fe == fun_en:
            return False
        add("민지", "en", "Okay, one more Did You Know, because this one is too good to skip.")
        add("알렉스", "en", fe)
        add("민지", "ko", fk)
        add("알렉스", "en", "Now you have a fun story for your next lesson. Try telling it to your tutor in English.")

    # (슬롯, 슬롯 안 순서, 함수) — 리스트 순서 = 넣는 우선순위, 슬롯 안 순서 = 방송에서 나오는 순서
    fillers = (("clinic", 0, f_clinic_more), ("game", 0, f_game2), ("clinic", 1, f_drill), ("why", 1, f_why2),
               ("clinic", 2, f_line), ("topic", 0, f_topic), ("why", 0, f_pattern), ("culture", 0, f_culture))
    slot_order = ("rewind", "game", "why", "clinic", "culture", "topic")
    extra = []

    def assemble():
        at = {}
        for name in slot_order:
            for _, _, ls in sorted((x for x in extra if x[0] == name), key=lambda x: x[1]):
                at.setdefault(slots[name], []).extend(ls)
        out = []
        for i in range(len(L) + 1):
            out += at.get(i, [])
            if i < len(L):
                out.append(L[i])
        return _tidy(out)

    script = assemble()
    for slot, pos, fn in fillers:
        if len(script) >= RADIO_MIN_LINES:
            break
        ls = capture(fn)
        if ls and len(script) + len(ls) <= RADIO_MAX_LINES:
            extra.append((slot, pos, ls))
            script = assemble()
    if len(script) < RADIO_MIN_LINES and rewind:     # 얇은 주: 늘리지 않고 짧은 회차라고 알린다
        extra.append(("rewind", -1, [("알렉스", "en", SHORT_SHOW_LINE)]))
        script = assemble()
    return script


def script_stats(lines):
    """대본 점검용: (총 줄 수, ko 줄 수, ko 비율)."""
    n = len(lines)
    ko = sum(1 for _, lang, _ in lines if lang == "ko")
    return n, ko, (ko / n if n else 0.0)


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

  <div class="card"><h2>📓 NotebookLM 팟캐스트로 듣기 <span class="sub">고품질·무료</span></h2>
    <div class="muted" style="margin-bottom:12px">이번 주 학습 다이제스트(교정·강사 피드백·어휘 전부)를 복사해 <b>NotebookLM</b>에 붙여넣고 <b>Audio Overview</b>를 만들면, 2인 진행 영어 팟캐스트가 무료로 생성됩니다(현재 TTS보다 자연스러움).</div>
    <div class="modes">
      <div class="mode" onclick="window.open('https://notebooklm.google.com/','_blank');copyDigest()"><span class="ico">📓</span>복사+NotebookLM 열기<span class="sub">원클릭 반자동</span></div>
      <div class="mode" onclick="copyDigest()"><span class="ico">📋</span>다이제스트만 복사<span class="sub">붙여넣기용 텍스트</span></div>
    </div>
  </div>

  <div class="foot">대본: scripts/build_radio.py · 다이제스트: scripts/build_digest.py · 음성: 브라우저 Web Speech(무료) · 주차별 누적 · 매주 금요일 Claude 갱신</div>
</div>

<pre id="radio-src" hidden>{esc(src)}</pre>
<div class="toast" id="toast">✅ 복사됐어요! Gemini에 붙여넣으세요</div>
<script>
const PAGE_WEEK={pw};
const PROMPTS={{chat:{P['chat']},lecture:{P['lecture']},radio:{P['radio']}}};
function showToast(m){{const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2500);}}
function copyOpen(mode){{const txt=PROMPTS[mode]||'';const go=()=>{{showToast('✅ 복사됐어요! Gemini에 붙여넣으세요');setTimeout(()=>window.open('https://gemini.google.com/app','_blank'),600);}};navigator.clipboard.writeText(txt).then(go).catch(()=>{{const a=document.createElement('textarea');a.value=txt;document.body.appendChild(a);a.select();document.execCommand('copy');a.remove();go();}});}}
function clip(txt,msg){{const go=()=>showToast(msg);navigator.clipboard.writeText(txt).then(go).catch(()=>{{const a=document.createElement('textarea');a.value=txt;document.body.appendChild(a);a.select();document.execCommand('copy');a.remove();go();}});}}
function copyDigest(){{fetch('digest-latest.txt',{{cache:'no-store'}}).then(r=>{{if(!r.ok)throw 0;return r.text();}}).then(t=>clip(t,'📓 다이제스트 복사됨! NotebookLM에 붙여넣으세요')).catch(()=>showToast('⚠️ 다이제스트가 아직 없어요 (금요일 생성)'));}}

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
    memos = load_carrot_memos()
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
    n_week, kept = 0, []
    for iso in ordered:
        if iso == latest:
            continue
        wk = weeks[iso]
        cum = [l for l in lessons if l["iso"] <= iso]      # 그 주말까지 누적
        default_src = _lines_to_src(build_script(iso, wk, cum, carrot_map, memos))
        src = resolve_src(iso, False, default_src)
        if src != default_src:
            kept.append(W.week_label(iso))
        prompts = build_chat_prompts(iso, wk, cum, carrot_map)
        page = render(iso, src, prompts, archive, is_hub=False)
        open(os.path.join(DOCS, radio_week_file(iso)), "w", encoding="utf-8").write(page)
        n_week += 1

    # 허브 = 가장 최근 주(라이브·Claude 갱신 대상·오디오 소스)
    wk = weeks[latest]
    default_src = _lines_to_src(build_script(latest, wk, lessons, carrot_map, memos))
    src = resolve_src(latest, True, default_src)
    hub_kept = src != default_src
    prompts = build_chat_prompts(latest, wk, lessons, carrot_map)
    page = render(latest, src, prompts, archive, is_hub=True)
    open(os.path.join(DOCS, "radio.html"), "w", encoding="utf-8").write(page)

    print(f"✅ radio.html(허브={W.week_label(latest)}) + 주차 스냅샷 {n_week}개 · 허브 대본 {len(src.splitlines())}줄"
          f" ({'기존 대본 보존' if hub_kept else '규칙기반 새 대본'})")
    print(f"   과거 주차: 기존 대본 보존(같은 주 대본이 이미 있음) {len(kept)}개 · 규칙기반 새로 씀 {n_week - len(kept)}개")
    for a in archive:
        tag = " (허브/현재)" if a["iso"] == latest else ""
        print(f"   {a['href']}  {a['lessons']}회{tag}")
    print(f"CURRENT_RADIO_FILE=radio.html")
    print(f"CURRENT_RADIO_WEEK={W.week_label(latest)}")


def preview(label):
    """그 주의 규칙기반 대본을 stdout 으로만 출력(페이지 파일은 건드리지 않음) + 줄 수·ko 비율은 stderr."""
    lessons = W.load_all()
    weeks = OrderedDict()
    for l in lessons:
        weeks.setdefault(l["iso"], []).append(l)
    iso = next((i for i in weeks if W.week_label(i) == label), None)
    if iso is None:
        sys.exit(f"❌ {label}: 그 주 수업 데이터 없음 (있는 주: {', '.join(W.week_label(i) for i in weeks)})")
    cum = [l for l in lessons if l["iso"] <= iso]
    lines = build_script(iso, weeks[iso], cum, W.load_carrot(), load_carrot_memos())
    print(_lines_to_src(lines))
    n, ko, r = script_stats(lines)
    print(f"# {label}: {n}줄 · ko {ko}줄 ({r:.0%})", file=sys.stderr)


if __name__ == "__main__":
    if "--preview" in sys.argv[1:]:
        preview(sys.argv[sys.argv.index("--preview") + 1])
    else:
        build()

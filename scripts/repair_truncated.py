#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
짤린 일일 복습 페이지 복구 도구 / Truncated daily review page repair.

배경 / Why:
  과거 토큰 한도가 낮아 긴 수업의 피드백 꼬리 섹션(실전 복습·자신감 충전·성과 지표)이
  잘린 채 게시된 페이지가 있다. 다행히 **전사(transcript)는 페이지에 온전히 임베드**되어
  있어, 원음(Drive) 없이도 페이지만으로 완전 복구가 가능하다.

동작 / How:
  짤린 페이지에서 전사·수업길이·파일명을 추출 → 새로 작성된 '완전한 7섹션 피드백'을 받아
  production 렌더러(process_lesson.generate_review_page)로 페이지를 통째로 재생성한다.
  → 비대해진 파일 크기도 정상화되고, 주간 복습 집계도 자동으로 온전해진다.
  피드백 작성 주체는 누구든 가능: Claude(직접/루틴), Gemini(--auto, API 키 필요).

CLI:
  python3 scripts/repair_truncated.py list
      짤린(꼬리 섹션 누락) 일일 페이지 날짜 목록 출력 (한 줄에 하나)
  python3 scripts/repair_truncated.py extract <YYYY-MM-DD>
      그 날짜 페이지의 메타(파일명·길이)와 전사를 출력 → 피드백 작성 입력용
  python3 scripts/repair_truncated.py apply <YYYY-MM-DD> <feedback.md>
      완전한 피드백 마크다운으로 페이지 재생성·덮어쓰기 (+ metadata.json 갱신)
  python3 scripts/repair_truncated.py auto <YYYY-MM-DD> [<YYYY-MM-DD> ...]
      각 날짜를 Gemini로 자동 재생성 (GEMINI_API_KEY 필요; 루틴/CI 무인 복구용)
"""
import sys, os, re, html, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
sys.path.insert(0, ROOT)

# process_lesson 은 모듈 최상단에서 일부 시크릿 env를 하드 요구한다(렌더링엔 불필요).
# 미설정 시 더미로 채워 import만 통과시킨다. 프로덕션엔 실제 값이 있어 덮어쓰지 않음.
for _k in ("GOOGLE_CREDENTIALS", "GROQ_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.setdefault(_k, "dummy")
import process_lesson as P  # noqa: E402

# 성숙 포맷(현행 프롬프트) 페이지면 반드시 있는 본문 마커.
#   둘 다 있어야 '복구 대상 포맷'으로 본다(구버전 포맷 오탐 방지).
INTRO_MARKERS = ("유창성 업그레이드", "한 놈만 패기")
# 온전한 피드백이면 반드시 있는 꼬리 마커 (없으면 짤림으로 판정)
TAIL_MARKERS = ("유창성 점수", "성과 지표")
SKIP = {"index.html"}                   # 일일 페이지가 아닌 것 제외


def _path(date):
    f = os.path.join(DOCS, f"{date}.html")
    if not os.path.exists(f):
        raise SystemExit(f"❌ 파일 없음: {f}")
    return f


def is_truncated(t):
    """성숙 포맷(현행 프롬프트) 페이지인데 꼬리 섹션 마커가 하나도 없으면 짤림.
    구버전 포맷(intro 마커 부재)은 복구 대상이 아니므로 False."""
    if not all(m in t for m in INTRO_MARKERS):
        return False
    return not any(m in t for m in TAIL_MARKERS)


def extract_transcript(t):
    m = (re.search(r'<div class="transcript">(.*?)</div>\s*</div>\s*<div class="toast"', t, re.S)
         or re.search(r'<div class="transcript">(.*?)</div>\s*</div>', t, re.S))
    if not m:
        return ""
    inner = re.sub(r'<span class="(?:tutor|student)">(\[[^\]]+\])</span>', r'\1', m.group(1))
    inner = re.sub(r'<[^>]+>', '', inner)
    return html.unescape(inner).strip()


def extract_duration(t):
    m = re.search(r'⏱\s*(\d+)\s*분\s*(\d+)\s*초', t)
    return (int(m.group(1)) * 60 + int(m.group(2))) if m else 0


def extract_filename(t):
    m = re.search(r'🎙\s*([^<]+?\.m4a)', t) or re.search(r'🎙\s*([^<\n]+)', t)
    return m.group(1).strip() if m else ""


def date_to_str(date):
    y, m, d = date.split("-")
    return f"{y}년 {m}월 {d}일"


def cmd_list():
    found = []
    for f in sorted(glob.glob(os.path.join(DOCS, "2026-*.html"))):
        if os.path.basename(f) in SKIP:
            continue
        if is_truncated(open(f, encoding="utf-8").read()):
            found.append(os.path.basename(f)[:10])
    print("\n".join(found) if found else "(짤린 페이지 없음)")
    return found


def cmd_extract(date):
    t = open(_path(date), encoding="utf-8").read()
    tr = extract_transcript(t)
    print(f"DATE={date}")
    print(f"FILENAME={extract_filename(t)}")
    print(f"DURATION_SEC={extract_duration(t)}")
    print(f"TRANSCRIPT_CHARS={len(tr)}")
    print("===TRANSCRIPT_BEGIN===")
    print(tr)
    print("===TRANSCRIPT_END===")


def _rebuild(date, feedback):
    f = _path(date)
    t = open(f, encoding="utf-8").read()
    tr = extract_transcript(t)
    if len(tr) < 500:
        raise SystemExit(f"❌ {date}: 전사 추출 실패/과소({len(tr)}자) — 페이지 복구 불가, 원음 재처리 필요")
    dur = extract_duration(t)
    fn = extract_filename(t) or f"{date}.m4a"
    page = P.generate_review_page(tr, feedback, fn, dur, date_to_str(date))
    open(f, "w", encoding="utf-8").write(page)
    # metadata.json 갱신 (index.html 통계·카테고리 정확성) — 순차 호출 전제(레이스 주의)
    try:
        meta = P.extract_metadata(feedback)
        P.save_metadata(DOCS, date, meta)
    except Exception as e:
        print(f"  ⚠️ metadata 갱신 건너뜀: {e}")
    print(f"✅ 재생성 완료: docs/{date}.html ({len(page)//1024}KB) · 전사 {len(tr):,}자 보존")


def cmd_apply(date, md_path):
    if not os.path.exists(md_path):
        raise SystemExit(f"❌ 피드백 파일 없음: {md_path}")
    feedback = open(md_path, encoding="utf-8").read().strip()
    if len(feedback) < 300:
        raise SystemExit(f"❌ 피드백이 너무 짧음({len(feedback)}자) — 완전한 7섹션인지 확인")
    _rebuild(date, feedback)


def cmd_auto(dates):
    """Gemini로 각 날짜를 자동 재생성 (무인 복구용). GEMINI_API_KEY 필요."""
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("❌ auto 모드는 GEMINI_API_KEY 필요 (루틴/CI 환경에서 실행)")
    for date in dates:
        t = open(_path(date), encoding="utf-8").read()
        tr = extract_transcript(t)
        print(f"🔁 {date}: Gemini로 피드백 재생성... (전사 {len(tr):,}자)")
        fb = P.generate_feedback(tr)
        fb = P.review_feedback(tr, fb)
        _rebuild(date, fb)


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return
    cmd = a[0].lstrip("-")
    if cmd == "list":
        cmd_list()
    elif cmd == "extract" and len(a) >= 2:
        cmd_extract(a[1])
    elif cmd == "apply" and len(a) >= 3:
        cmd_apply(a[1], a[2])
    elif cmd == "auto" and len(a) >= 2:
        cmd_auto(a[1:])
    else:
        raise SystemExit("사용법: list | extract <date> | apply <date> <feedback.md> | auto <date...>")


if __name__ == "__main__":
    main()

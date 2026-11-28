#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📓 노션 '영어복습' 기록기 / push daily lesson pages to Notion.

복습 페이지(docs/<날짜>.html)의 'AI 피드백'과 '수업 전사'를 노션 「영어복습」 페이지 아래에
하루 한 페이지로 올린다. Codex 같은 AI 가 그 기록을 읽고 사용자와 말로 복습한다
(진행 가이드는 노션 「영어복습」 페이지 맨 위에 있다).

- 이미 올라간 날짜는 건너뛴다(하위 페이지 제목의 날짜로 판별) → 여러 번 돌려도 중복이 없다.
- 빠진 날은 다음 실행이 메운다(SINCE 이후의 모든 복습 페이지를 본다).
- 꼬리가 잘린 페이지는 올리지 않고 미룬다(금요일 루틴이 고친 뒤 다음 실행이 올린다).
- 올리다 실패한 페이지는 제목 앞에 ⏳ 가 남고, 다음 실행이 지우고 처음부터 다시 올린다.
- NOTION_TOKEN 이 없으면 아무것도 하지 않고 정상 종료한다.
- 순수 표준 라이브러리. 네트워크는 api.notion.com 만 쓴다.

설정 (한 번만) / one-time setup:
  1. notion.so/profile/integrations 에서 내부 연결(internal integration)을 만들고 토큰을 복사한다.
  2. 노션 「영어복습」 페이지의 ••• → 연결(Connections) 에서 그 연결을 추가한다(하위 페이지에도 적용된다).
  3. GitHub 저장소 Settings → Secrets and variables → Actions 에 NOTION_TOKEN 이름으로 토큰을 넣는다.
  매일 도는 english-feedback.yml 의 '📓 노션 영어복습 기록' 단계가 이 스크립트를 부른다.

사용 / usage:
  python scripts/push_notion.py              # SINCE 이후 빠진 날 전부
  python scripts/push_notion.py 2026-11-27   # 그 날짜(파일 이름)만
  python scripts/push_notion.py --dry-run    # 올리지 않고 무엇을 올릴지만 출력 (네트워크 미사용)

Pushes each daily review page to a private Notion page as one child page per lesson.
Idempotent (dedupes by title date), self-healing (re-scans since SINCE), stdlib only.
"""
import argparse
import datetime
import glob
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"
# 노션 「영어복습」 페이지. 비밀값이 아니다(토큰과 연결 허용이 없으면 열리지 않는다).
DEFAULT_PARENT = "425be575bcf881208622cdd6415c5fd0"
# 이 날짜부터만 올린다 — 과거 수업은 옮기지 않기로 했다(2026-11-27 결정).
DEFAULT_SINCE = "2026-11-26"
DEFAULT_PAGES_URL = "https://ok0327-dot.github.io/english-feedback"

WEEKDAYS = "월화수목금토일"
PENDING = "⏳ "                       # 올리는 중(또는 올리다 실패한) 페이지의 제목 머리표
MAX_CHILDREN = 100                    # 요청 한 번에 넣을 수 있는 덩어리 수 (Notion 제한)
MAX_TEXT_UNITS = 1900                 # 글 조각 하나의 길이 (Notion 제한 2000, 여유를 둔다)
MAX_RICH_TEXT = 100                   # 덩어리 하나에 넣을 수 있는 글 조각 수 (Notion 제한)

# scripts/repair_truncated.py 의 판별 기준과 같다(그 파일은 process_lesson 을 불러와 무거워서 복사).
INTRO_MARKERS = ("유창성 업그레이드", "한 놈만 패기")
TAIL_MARKERS = ("유창성 점수", "성과 지표")

SLUG_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-(\d+))?$")
TITLE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) \(.\)(?: #(\d+))?")


class Postpone(Exception):
    """지금은 올리지 않고 다음 실행으로 미룬다(실패가 아니다)."""


class NotionError(Exception):
    pass


# ══════════════════════════════════════════════════════════════════
# 1) 복습 페이지 HTML → 덩어리 목록
#    덩어리: ("h"|"p"|"li"|"quote", [조각...])  또는  ("table", [[[조각...], ...], ...])
#    조각:   (글자, 굵게?, 코드?, 링크 또는 None)
# ══════════════════════════════════════════════════════════════════
_INLINE = re.compile(r"<strong>(.*?)</strong>|<code>(.*?)</code>", re.S)
_ANY_TAG = re.compile(r"</?(?:span|div|p|details|summary|br|strong|code|h2)\b[^>]*>")


def _runs(text):
    """한 줄 안의 <strong>·<code> 를 조각으로 나눈다. 나머지 태그는 떼어 낸다."""
    text = text.replace('<span class="arrow">→</span>', "→")
    parts, pos = [], 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            parts.append((text[pos:m.start()], False, False))
        if m.group(1) is not None:
            parts.append((m.group(1), True, False))
        else:
            parts.append((m.group(2), False, True))
        pos = m.end()
    if pos < len(text):
        parts.append((text[pos:], False, False))
    out = []
    for t, bold, code in parts:
        t = html.unescape(_ANY_TAG.sub("", t))
        if t:
            out.append((t, bold, code, None))
    return out


def _inside(page, open_tag, start_id):
    """id=start_id 구역 안에서 open_tag 바로 뒤의 내용을 돌려준다."""
    i = page.find(f'id="{start_id}"')
    if i < 0:
        raise Postpone(f"'{start_id}' 구역이 없습니다")
    k = page.find(open_tag, i)
    if k < 0:
        raise Postpone(f"'{start_id}' 구역의 본문이 없습니다")
    return page[k + len(open_tag):]


def parse_feedback(page):
    body = _inside(page, '<div class="feedback">', "tab-feedback")
    end = body.find('id="tab-transcript"')
    if end < 0:
        raise Postpone("'tab-transcript' 구역이 없습니다")
    body = body[:end]
    body = body[: body.rfind("<div")]  # 구역 끝에 딸려 오는 다음 탭의 "<div" 조각을 뗀다
    blocks, rows = [], None
    for line in body.split("\n"):
        line = line.strip()
        if line.startswith("<table>"):
            rows = []
            continue
        if line.startswith("</table>"):
            if rows:
                blocks.append(("table", rows))
            rows = None
            continue
        if rows is not None and line.startswith("<tr>"):
            rows.append([_runs(c) for c in re.findall(r"<t[hd]>(.*?)</t[hd]>", line, re.S)])
            continue
        if not line or line == "<br>":
            continue
        m = re.match(r"<h2>(.*)</h2>$", line)
        if m:
            blocks.append(("h", _runs(m.group(1))))
            continue
        m = re.match(r'<div class="numbered"><strong>(\d+)\.</strong>\s*(.*)</div>$', line)
        if m:  # 번호 목록은 번호를 글자로 남긴다(목록으로 만들면 매번 1번부터 다시 센다)
            blocks.append(("p", [(m.group(1) + ". ", False, False, None)] + _runs(m.group(2))))
            continue
        m = re.match(r'<div class="item">(.*)</div>$', line)
        if m:
            blocks.append(("li", _runs(m.group(1))))
            continue
        m = re.match(r"<p>(.*)</p>(?:</div>)?$", line)
        if m:
            inner = m.group(1)
            if inner.startswith(">"):
                kind, runs = "quote", _runs(inner.lstrip("> "))
            elif re.match(r"<strong>\d+\.\s[^<]*</strong>$", inner):
                kind, runs = "h", _runs(inner)  # "1. 📊 오늘의 대화 요약" 같은 항목 제목
            else:
                kind, runs = "p", _runs(inner)
            if runs:
                blocks.append((kind, runs))
            continue
        runs = _runs(line)  # 예상 밖의 줄(details 등)은 글자만 남긴다
        if runs:
            blocks.append(("p", runs))
    return blocks


def parse_transcript(page):
    body = _inside(page, '<div class="transcript">', "tab-transcript")
    end = body.find("</div>")  # 전사 안에는 div 가 없다 → 첫 닫는 태그가 끝
    if end < 0:
        raise Postpone("수업 전사의 끝을 찾지 못했습니다")
    blocks = []
    for para in re.split(r"\n\s*\n", body[:end]):
        para = para.strip()
        if not para:
            continue
        m = re.match(r'<span class="(?:student|tutor)">\[(\w+)\]</span>\s*(.*)$', para, re.S)
        if m:
            text = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
            blocks.append(("p", [(m.group(1) + ":", True, False, None), (" " + text, False, False, None)]))
        else:
            text = html.unescape(re.sub(r"<[^>]+>", "", para)).strip()
            if text:
                blocks.append(("p", [(text, False, False, None)]))
    return blocks


def slug_key(slug):
    """'2026-08-17-2' → ('2026-08-17', 2). 복습 페이지 이름이 아니면 None."""
    m = SLUG_RE.match(slug)
    return (m.group(1), int(m.group(2) or 1)) if m else None


def title_key(title):
    """'2026-08-17 (월) #2 주제' → ('2026-08-17', 2). 수업 페이지 제목이 아니면 None."""
    m = TITLE_RE.match(title)
    return (m.group(1), int(m.group(2) or 1)) if m else None


def build_lesson(slug, docs_dir=DOCS, pages_url=DEFAULT_PAGES_URL, guide_url=None):
    """복습 페이지 하나를 (제목, 덩어리 목록)으로 만든다. 올리기에 모자라면 Postpone.
    guide_url 은 진행 안내가 있는 상위 「영어복습」 페이지 주소 — 수업 페이지로 바로 들어온 AI 가 안내를 찾게 한다."""
    key = slug_key(slug)
    if not key:
        raise Postpone("복습 페이지 이름이 아닙니다")
    date, number = key
    with open(os.path.join(docs_dir, slug + ".html"), encoding="utf-8") as f:
        page = f.read()
    if all(m in page for m in INTRO_MARKERS) and not any(m in page for m in TAIL_MARKERS):
        raise Postpone("피드백 꼬리가 잘린 페이지입니다(고쳐진 뒤 올립니다)")
    feedback, transcript = parse_feedback(page), parse_transcript(page)
    if len(feedback) < 10:
        raise Postpone(f"피드백이 너무 짧습니다({len(feedback)}덩어리)")
    turns = sum(1 for _, runs in transcript if len(runs) == 2)
    if turns < 5:
        raise Postpone(f"수업 전사에 화자 구분이 거의 없습니다({turns}턴)")

    topic = ""
    data_path = os.path.join(docs_dir, "data", slug + ".json")
    if os.path.exists(data_path):
        try:
            with open(data_path, encoding="utf-8") as f:
                topic = (json.load(f).get("topic") or "").strip()
        except (OSError, ValueError):
            topic = ""
    y, mo, d = (int(x) for x in date.split("-"))
    weekday = WEEKDAYS[datetime.date(y, mo, d).weekday()]
    title = f"{date} ({weekday})" + (f" #{number}" if number > 1 else "") + (f" {topic}" if topic else "")

    m = re.search(r"<span>⏱\s*([^<]+)</span>", page)
    head = [(f"수업일 {date} ({weekday})" + (f" · 수업 길이 {m.group(1).strip()}" if m else "") + " · ",
             False, False, None),
            ("원본 복습 페이지", False, False, f"{pages_url.rstrip('/')}/{slug}.html")]
    pointer = [("🤖 이 기록으로 복습할 때는 상위 페이지 ", False, False, None),
               ("「영어복습」 맨 위 안내", False, False, guide_url),
               ("를 먼저 읽고 그대로 진행한다.", False, False, None)]
    blocks = [("p", head), ("p", pointer), ("h2", [("AI 피드백", False, False, None)])]
    blocks += feedback
    blocks += [("h2", [("수업 전사", False, False, None)]),
               ("p", [("Student 가 사용자, Tutor 가 강사입니다. [?] 는 잘 안 들린 부분입니다.", False, False, None)])]
    blocks += transcript
    return title, blocks


# ══════════════════════════════════════════════════════════════════
# 2) 덩어리 목록 → Notion API 요청 모양
# ══════════════════════════════════════════════════════════════════
def _units(ch):
    return 2 if ord(ch) > 0xFFFF else 1  # Notion 은 길이를 UTF-16 단위로 센다고 보고 넉넉히 자른다


def _split(text, limit=MAX_TEXT_UNITS):
    out, cur, used = [], [], 0
    for ch in text:
        u = _units(ch)
        if used + u > limit:
            out.append("".join(cur))
            cur, used = [], 0
        cur.append(ch)
        used += u
    if cur:
        out.append("".join(cur))
    return out


def rich_text(runs):
    items = []
    for text, bold, code, link in runs:
        for piece in _split(text):
            item = {"type": "text", "text": {"content": piece}}
            if link:
                item["text"]["link"] = {"url": link}
            if bold or code:
                item["annotations"] = {"bold": bool(bold), "italic": False, "strikethrough": False,
                                       "underline": False, "code": bool(code), "color": "default"}
            items.append(item)
    if len(items) > MAX_RICH_TEXT:  # 조각이 너무 많으면 꾸밈을 버리고 글자만 남긴다
        plain = "".join(t for t, _, _, _ in runs)
        items = [{"type": "text", "text": {"content": p}} for p in _split(plain)][:MAX_RICH_TEXT]
    return items


_KINDS = {"p": "paragraph", "li": "bulleted_list_item", "quote": "quote", "h": "heading_3", "h2": "heading_2"}


def to_notion(blocks):
    out = []
    for kind, data in blocks:
        if kind == "table":
            width = max(len(row) for row in data)
            rows = [{"type": "table_row",
                     "table_row": {"cells": [rich_text(c) for c in row] + [[] for _ in range(width - len(row))]}}
                    for row in data][:MAX_CHILDREN]
            out.append({"type": "table",
                        "table": {"table_width": width, "has_column_header": True,
                                  "has_row_header": False, "children": rows}})
            continue
        rt = rich_text(data)
        if rt:
            name = _KINDS[kind]
            out.append({"type": name, name: {"rich_text": rt}})
    return out


# ══════════════════════════════════════════════════════════════════
# 3) Notion API
# ══════════════════════════════════════════════════════════════════
def _http_send(method, url, headers, data):
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


class Notion:
    """필요한 호출만 감싼 얇은 클라이언트. send·sleep 은 시험에서 가짜로 바꾼다."""

    def __init__(self, token, send=_http_send, sleep=time.sleep):
        self._token, self._send, self._sleep = token, send, sleep

    def call(self, method, path, body=None):
        headers = {"Authorization": f"Bearer {self._token}", "Notion-Version": NOTION_VERSION,
                   "Content-Type": "application/json"}
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        waited = 0
        for attempt in range(6):
            try:
                status, resp_headers, raw = self._send(method, NOTION_API + path, headers, data)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                # 쓰기 요청은 서버에 닿았는지 알 수 없다 → 다시 보내면 중복이 생길 수 있어 그만둔다
                if method != "GET" or attempt >= 2:
                    raise NotionError(f"{method} {path}: 연결 실패 ({type(e).__name__})")
                self._sleep(2 * (attempt + 1))
                continue
            if 200 <= status < 300:
                self._sleep(0.35)  # 평균 초당 3회 제한 안쪽으로
                return json.loads(raw.decode("utf-8")) if raw else {}
            # 429(한도)·529(과부하)는 처리되지 않은 요청이다 → 기다렸다 다시 보내도 안전하다
            if status in (429, 529) and attempt < 5 and waited < 90:
                try:
                    wait = int(resp_headers.get("Retry-After") or resp_headers.get("retry-after") or 2)
                except ValueError:
                    wait = 2
                wait = max(1, min(wait, 30))
                waited += wait
                self._sleep(wait)
                continue
            if method == "GET" and status >= 500 and attempt < 2:
                self._sleep(2 * (attempt + 1))
                continue
            try:
                message = json.loads(raw.decode("utf-8")).get("message", "")
            except (ValueError, AttributeError):
                message = ""
            raise NotionError(f"{method} {path}: HTTP {status} {message[:200]}")
        raise NotionError(f"{method} {path}: 재시도 한도 초과")

    def child_pages(self, parent):
        """parent 바로 아래 하위 페이지의 (id, 제목) 목록 — 휴지통에 있는 것은 뺀다."""
        pages, cursor = [], None
        while True:
            path = f"/blocks/{parent}/children?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
            res = self.call("GET", path)
            for block in res.get("results", []):
                if block.get("type") == "child_page" and not block.get("in_trash"):
                    pages.append((block["id"], block["child_page"].get("title", "")))
            if not res.get("has_more"):
                return pages
            cursor = res.get("next_cursor")

    def create_page(self, parent, title, children):
        res = self.call("POST", "/pages", {"parent": {"page_id": parent},
                                           "properties": {"title": _title(title)},
                                           "children": children})
        return res["id"]

    def append(self, page_id, children):
        self.call("PATCH", f"/blocks/{page_id}/children", {"children": children})

    def rename(self, page_id, title):
        self.call("PATCH", f"/pages/{page_id}", {"properties": {"title": _title(title)}})

    def trash(self, page_id):
        self.call("PATCH", f"/pages/{page_id}", {"in_trash": True})


def _title(text):
    return {"title": [{"type": "text", "text": {"content": text[:MAX_TEXT_UNITS]}}]}


def push_lesson(api, parent, title, blocks):
    """수업 페이지 하나를 올린다. 끝까지 올라간 뒤에야 ⏳ 를 떼므로, 중간에 끊긴 페이지는 완성본으로 세지 않는다."""
    children = to_notion(blocks)
    page_id = api.create_page(parent, PENDING + title, children[:MAX_CHILDREN])
    try:
        for i in range(MAX_CHILDREN, len(children), MAX_CHILDREN):
            api.append(page_id, children[i:i + MAX_CHILDREN])
        api.rename(page_id, title)
    except NotionError:
        try:
            api.trash(page_id)  # 반쯤 올라간 페이지를 치운다(안 되면 다음 실행이 ⏳ 를 보고 치운다)
        except NotionError:
            pass
        raise
    return page_id, len(children)


# ══════════════════════════════════════════════════════════════════
# 4) 실행
# ══════════════════════════════════════════════════════════════════
def candidates(docs_dir, since, only=None):
    """올릴 후보 복습 페이지 이름(날짜순). only 를 주면 그것만."""
    if only:
        return sorted(only, key=lambda s: slug_key(s) or (s, 0))
    found = []
    for path in glob.glob(os.path.join(docs_dir, "20??-??-??*.html")):
        slug = os.path.splitext(os.path.basename(path))[0]
        key = slug_key(slug)
        if key and key[0] >= since:
            found.append((key, slug))
    return [slug for _, slug in sorted(found)]


def run(api, parent, slugs, docs_dir=DOCS, pages_url=DEFAULT_PAGES_URL, dry_run=False, log=print):
    """(올린 수, 미룬 수, 실패 수)를 돌려준다."""
    have = set()
    if not dry_run:
        for page_id, title in api.child_pages(parent):
            if title.startswith(PENDING) and title_key(title[len(PENDING):]):
                log(f"🧹 올리다 만 페이지를 치웁니다: {title}")
                api.trash(page_id)
                continue
            key = title_key(title)
            if key:
                have.add(key)
    pushed = postponed = failed = 0
    guide_url = "https://www.notion.so/" + parent.replace("-", "")
    for slug in slugs:
        if slug_key(slug) in have:
            continue
        try:
            title, blocks = build_lesson(slug, docs_dir, pages_url, guide_url)
        except Postpone as e:
            postponed += 1
            log(f"⏸️ {slug}: 미룸 — {e}")
            continue
        except OSError as e:
            failed += 1
            log(f"❌ {slug}: 복습 페이지를 읽지 못했습니다 ({type(e).__name__})")
            continue
        if dry_run:
            log(f"📝 {slug}: 올릴 예정 — {title} ({len(to_notion(blocks))}덩어리)")
            continue
        try:
            _, count = push_lesson(api, parent, title, blocks)
        except NotionError as e:
            failed += 1
            log(f"❌ {slug}: 노션에 올리지 못했습니다 — {e}")
            continue
        pushed += 1
        have.add(slug_key(slug))
        log(f"📓 {slug}: 노션에 올렸습니다 — {title} ({count}덩어리)")
    return pushed, postponed, failed


def main(argv=None):
    ap = argparse.ArgumentParser(description="복습 페이지를 노션 「영어복습」에 하루 한 페이지로 올린다")
    ap.add_argument("slugs", nargs="*", help="올릴 복습 페이지 이름(예: 2026-11-27). 비우면 SINCE 이후 빠진 날 전부")
    ap.add_argument("--since", default=os.environ.get("NOTION_SINCE") or DEFAULT_SINCE)
    ap.add_argument("--dry-run", action="store_true", help="올리지 않고 무엇을 올릴지만 출력 (네트워크 미사용)")
    args = ap.parse_args(argv)

    token = (os.environ.get("NOTION_TOKEN") or "").strip()
    if not token and not args.dry_run:
        print("ℹ️ NOTION_TOKEN 미설정 — 노션 기록 건너뜀")
        return 0
    parent = (os.environ.get("NOTION_PARENT_PAGE_ID") or DEFAULT_PARENT).strip()
    pages_url = (os.environ.get("GITHUB_PAGES_URL") or DEFAULT_PAGES_URL).strip()
    slugs = candidates(DOCS, args.since, args.slugs)
    if not slugs:
        print("ℹ️ 올릴 복습 페이지가 없습니다")
        return 0
    try:
        pushed, postponed, failed = run(Notion(token), parent, slugs, DOCS, pages_url, args.dry_run)
    except NotionError as e:
        print(f"❌ 노션에 연결하지 못했습니다 — {e}")
        return 1
    print(f"✅ 노션 기록: 새로 올림 {pushed} · 미룸 {postponed} · 실패 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

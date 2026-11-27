#!/usr/bin/env python3
"""
노션 '영어복습' 기록기(scripts/push_notion.py) 검사 / tests for the Notion lesson pusher.

핵심: ① 복습 페이지가 빠짐없이 덩어리로 바뀐다 ② 여러 번 돌려도 중복이 없다
     ③ 올리다 끊기면 반쪽 페이지가 완성본으로 남지 않고 다음 실행이 다시 올린다
     ④ 사용자가 직접 만든 다른 페이지는 건드리지 않는다.
가짜 노션 서버로 재현한다.
실행 / run:  python3 tests/test_push_notion.py   (pytest 불필요, 네트워크 미사용)
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import push_notion as pn  # noqa: E402

PARENT = "parent-page"


# ── 가짜 복습 페이지 ───────────────────────────────────────────────
def make_page(extra_feedback="", turns=8, tail=True, long_turn=""):
    feedback = [
        "<p><strong>0. 📌 Topic</strong></p>",
        "<p>Topic: Test Topic</p>",
        "<br>",
        "<p><strong>2. 💬 유창성 업그레이드 (Fluency & Natural Flow)</strong></p>",
        "<p><strong>① 어제 갔다고 말할 때</strong></p>",
        '<div class="item">❌ As Said: "I go yesterday."</div>',
        '<div class="item">✅ Natural: "I went yesterday."</div>',
        '<p><span class="arrow">→</span> <strong>went</strong> 를 통째로 익히세요. <code>go/went</code></p>',
        "<br>",
        "<p><strong>3. 🔧 고질적 문법 '한 놈만 패기' (Target Grammar)</strong></p>",
        "<table>",
        "<tr><th>❌ 원문 (As Said)</th><th>✅ 교정 (Corrected)</th></tr>",
        '<tr><td>"two question"</td><td>"two question<strong>s</strong>"</td></tr>',
        "</table>",
        '<div class="numbered"><strong>1.</strong> 첫째 줄</div>',
        "<p>> ✅ I prepared some questions.</p>",
        "<h2>옛 형식 제목</h2>",
        extra_feedback,
    ]
    if tail:
        feedback += ["<p><strong>[성과 지표]</strong></p>", "<p>📈 <strong>유창성 점수: 6 / 10</strong></p>"]
    lines = []
    for i in range(turns):
        who, cls = ("Student", "student") if i % 2 == 0 else ("Tutor", "tutor")
        text = long_turn if (long_turn and i == 2) else f"It&#x27;s turn {i}. [?]"
        lines.append(f'<span class="{cls}">[{who}]</span> {text}')
    return (
        '<html><body><div class="header"><div class="header-meta"><span>⏱ 20분 1초</span></div></div>\n'
        '<div class="container">\n'
        '        <div id="tab-feedback" class="tab-content active">\n'
        '            <div class="feedback">' + "\n".join(x for x in feedback if x) + "</div>\n"
        "        </div>\n"
        '        <div id="tab-transcript" class="tab-content">\n'
        '            <div class="transcript">' + "\n\n".join(lines) + "</div>\n"
        "        </div>\n"
        '</div><div class="toast" id="toast">x</div></body></html>'
    )


def make_docs(pages, topics=None):
    d = tempfile.mkdtemp(prefix="pn-test-")
    os.makedirs(os.path.join(d, "data"))
    for slug, page in pages.items():
        with open(os.path.join(d, slug + ".html"), "w", encoding="utf-8") as f:
            f.write(page)
        with open(os.path.join(d, "data", slug + ".json"), "w", encoding="utf-8") as f:
            json.dump({"topic": (topics or {}).get(slug, "Test Topic")}, f)
    return d


# ── 가짜 노션 서버 ─────────────────────────────────────────────────
def _utf16(s):
    return len(s.encode("utf-16-le")) // 2


class FakeNotion:
    """api.notion.com 흉내. Notion 의 요청 제한(덩어리 100개·글 2000자·조각 100개)을 어기면 400."""

    def __init__(self):
        self.pages = {}        # id → {"title", "parent", "children", "in_trash"}
        self.order = []        # 만든 순서
        self.calls = []        # (method, path)
        self.fail = []         # [(method, path 앞부분, status, headers)] — 맞는 첫 요청에 한 번씩 쓴다
        self.sleeps = []
        self._n = 0

    def add_page(self, title, parent=PARENT, in_trash=False):
        self._n += 1
        pid = f"page-{self._n}"
        self.pages[pid] = {"title": title, "parent": parent, "children": [], "in_trash": in_trash}
        self.order.append(pid)
        return pid

    def live_titles(self):
        return [self.pages[p]["title"] for p in self.order
                if self.pages[p]["parent"] == PARENT and not self.pages[p]["in_trash"]]

    def sleep(self, seconds):
        self.sleeps.append(seconds)

    def _check(self, children):
        if len(children) > 100:
            return "too many children"
        for block in children:
            body = block[block["type"]]
            texts = [body.get("rich_text", [])]
            if block["type"] == "table":
                rows = body["children"]
                if not rows or any(len(r["table_row"]["cells"]) != body["table_width"] for r in rows):
                    return "bad table"
                texts = [cell for r in rows for cell in r["table_row"]["cells"]]
            for rt in texts:
                if len(rt) > 100 or any(_utf16(x["text"]["content"]) > 2000 for x in rt):
                    return "rich text too long"
        return None

    def send(self, method, url, headers, data):
        assert url.startswith(pn.NOTION_API), url
        assert headers["Authorization"] == "Bearer test-token"
        assert headers["Notion-Version"] == pn.NOTION_VERSION
        path = url[len(pn.NOTION_API):]
        self.calls.append((method, path))
        for i, (m, prefix, status, hdrs) in enumerate(self.fail):
            if m == method and path.startswith(prefix):
                del self.fail[i]
                return status, hdrs, json.dumps({"message": "boom"}).encode()
        body = json.loads(data.decode("utf-8")) if data else None

        def ok(obj):
            return 200, {}, json.dumps(obj).encode()

        if method == "GET" and path.startswith("/blocks/"):
            parent = path.split("/")[2]
            query = path.partition("?")[2]
            start = 0
            for part in query.split("&"):
                if part.startswith("start_cursor="):
                    start = int(part.split("=")[1])
            kids = [p for p in self.order if self.pages[p]["parent"] == parent]
            chunk = kids[start:start + 2]  # 일부러 2개씩만 주어 이어 받기를 검사한다
            more = start + 2 < len(kids)
            return ok({"results": [{"id": p, "type": "child_page", "in_trash": self.pages[p]["in_trash"],
                                    "child_page": {"title": self.pages[p]["title"]}} for p in chunk],
                       "has_more": more, "next_cursor": str(start + 2) if more else None})
        if method == "POST" and path == "/pages":
            err = self._check(body["children"])
            if err:
                return 400, {}, json.dumps({"message": err}).encode()
            pid = self.add_page(body["properties"]["title"]["title"][0]["text"]["content"],
                                body["parent"]["page_id"])
            self.pages[pid]["children"] += body["children"]
            return ok({"id": pid})
        if method == "PATCH" and path.startswith("/blocks/"):
            err = self._check(body["children"])
            if err:
                return 400, {}, json.dumps({"message": err}).encode()
            self.pages[path.split("/")[2]]["children"] += body["children"]
            return ok({})
        if method == "PATCH" and path.startswith("/pages/"):
            page = self.pages[path.split("/")[2]]
            if "in_trash" in body:
                page["in_trash"] = body["in_trash"]
            if "properties" in body:
                page["title"] = body["properties"]["title"]["title"][0]["text"]["content"]
            return ok({})
        return 404, {}, b"{}"


def client(fake):
    return pn.Notion("test-token", send=fake.send, sleep=fake.sleep)


def run(fake, docs, slugs=None):
    logs = []
    slugs = slugs or pn.candidates(docs, "2026-11-26")
    result = pn.run(client(fake), PARENT, slugs, docs, "https://example.test", log=logs.append)
    return result, logs


def plain(block):
    body = block[block["type"]]
    return "".join(x["text"]["content"] for x in body.get("rich_text", []))


# ── 검사 ───────────────────────────────────────────────────────────
def test_page_becomes_blocks():
    docs = make_docs({"2026-11-27": make_page()})
    title, blocks = pn.build_lesson("2026-11-27", docs, "https://example.test")
    assert title == "2026-11-27 (금) Test Topic", title
    out = pn.to_notion(blocks)
    kinds = [b["type"] for b in out]
    texts = [plain(b) for b in out]
    assert kinds[0] == "paragraph" and "수업 길이 20분 1초" in texts[0]
    assert out[0]["paragraph"]["rich_text"][-1]["text"]["link"]["url"] == "https://example.test/2026-11-27.html"
    assert texts[1] == "AI 피드백" and kinds[1] == "heading_2"
    assert "0. 📌 Topic" in texts and kinds[texts.index("0. 📌 Topic")] == "heading_3"
    assert '❌ As Said: "I go yesterday."' in texts
    assert kinds[texts.index('❌ As Said: "I go yesterday."')] == "bulleted_list_item"
    arrow = out[texts.index("→ went 를 통째로 익히세요. go/went")]["paragraph"]["rich_text"]
    assert any(x["text"]["content"] == "went" and x["annotations"]["bold"] for x in arrow)
    assert any(x["text"]["content"] == "go/went" and x["annotations"]["code"] for x in arrow)
    table = out[kinds.index("table")]["table"]
    assert table["table_width"] == 2 and len(table["children"]) == 2
    assert "1. 첫째 줄" in texts
    assert kinds[texts.index("✅ I prepared some questions.")] == "quote"
    assert "옛 형식 제목" in texts
    assert "수업 전사" in texts
    turns = [t for t in texts if t.startswith(("Student:", "Tutor:"))]
    assert len(turns) == 8 and turns[0] == "Student: It's turn 0. [?]", turns[:1]
    assert not any("<" in t and ">" in t for t in texts), "HTML 태그가 남았다"


def test_long_text_is_split_without_loss():
    long_turn = ("가나다 abc 😀 " * 700).strip()  # 약 7천 글자 + 이모지
    docs = make_docs({"2026-11-27": make_page(long_turn=long_turn)})
    _, blocks = pn.build_lesson("2026-11-27", docs)
    out = pn.to_notion(blocks)
    block = next(b for b in out if "가나다 abc" in plain(b))
    pieces = block["paragraph"]["rich_text"]
    assert len(pieces) > 3 and all(_utf16(x["text"]["content"]) <= 2000 for x in pieces)
    assert plain(block) == "Student: " + long_turn


def test_push_in_chunks_and_idempotent():
    extra = "\n".join(f'<div class="item">줄 {i}</div>' for i in range(230))
    docs = make_docs({"2026-11-27": make_page(extra_feedback=extra)})
    fake = FakeNotion()
    (pushed, postponed, failed), _ = run(fake, docs)
    assert (pushed, postponed, failed) == (1, 0, 0)
    assert fake.live_titles() == ["2026-11-27 (금) Test Topic"]
    page = fake.pages["page-1"]
    _, blocks = pn.build_lesson("2026-11-27", docs, "https://example.test")
    assert page["children"] == pn.to_notion(blocks), "덩어리 순서·내용이 그대로 올라가야 한다"
    assert len(page["children"]) > 200
    writes = [c for c in fake.calls if c[0] != "GET"]
    assert writes[0] == ("POST", "/pages") and writes[-1] == ("PATCH", "/pages/page-1")
    assert sum(1 for c in writes if c[1].startswith("/blocks/")) == 2  # 100 + 100 + 나머지

    before = len(fake.calls)
    (pushed, postponed, failed), _ = run(fake, docs)
    assert (pushed, postponed, failed) == (0, 0, 0)
    assert all(c[0] == "GET" for c in fake.calls[before:]), "두 번째 실행은 읽기만 해야 한다"
    assert fake.live_titles() == ["2026-11-27 (금) Test Topic"]


def test_existing_and_user_pages_untouched():
    docs = make_docs({"2026-11-26": make_page(), "2026-11-27": make_page()})
    fake = FakeNotion()
    fake.add_page("메모")                                   # 사용자가 직접 만든 페이지
    fake.add_page("2026-11-26 (목) 손으로 올린 수업")          # 이미 올라간 날
    fake.add_page("⏳ 나중에 볼 것")                          # ⏳ 로 시작하지만 수업 페이지가 아니다
    (pushed, postponed, failed), _ = run(fake, docs)
    assert (pushed, postponed, failed) == (1, 0, 0)
    assert fake.live_titles() == ["메모", "2026-11-26 (목) 손으로 올린 수업", "⏳ 나중에 볼 것",
                                  "2026-11-27 (금) Test Topic"]
    assert not any(c[0] == "PATCH" and c[1] in ("/pages/page-1", "/pages/page-2", "/pages/page-3")
                   for c in fake.calls)


def test_failure_midway_leaves_no_half_page():
    extra = "\n".join(f'<div class="item">줄 {i}</div>' for i in range(150))
    docs = make_docs({"2026-11-27": make_page(extra_feedback=extra)})
    fake = FakeNotion()
    fake.fail.append(("PATCH", "/blocks/", 500, {}))        # 이어 붙이다 서버 오류
    (pushed, postponed, failed), logs = run(fake, docs)
    assert (pushed, postponed, failed) == (0, 0, 1), logs
    assert fake.live_titles() == [], "반쪽 페이지가 남으면 안 된다"
    assert sum(1 for c in fake.calls if c[0] == "PATCH" and c[1].startswith("/blocks/")) == 1, "쓰기는 재시도하지 않는다"

    (pushed, postponed, failed), _ = run(fake, docs)        # 다음 실행이 처음부터 다시 올린다
    assert (pushed, postponed, failed) == (1, 0, 0)
    assert fake.live_titles() == ["2026-11-27 (금) Test Topic"]


def test_leftover_pending_page_is_replaced():
    docs = make_docs({"2026-11-27": make_page()})
    fake = FakeNotion()
    fake.add_page("⏳ 2026-11-27 (금) Test Topic")           # 지난번에 치우지도 못한 반쪽 페이지
    (pushed, postponed, failed), _ = run(fake, docs)
    assert (pushed, postponed, failed) == (1, 0, 0)
    assert fake.live_titles() == ["2026-11-27 (금) Test Topic"]
    assert fake.pages["page-1"]["in_trash"] is True


def test_rate_limit_is_retried():
    docs = make_docs({"2026-11-27": make_page()})
    fake = FakeNotion()
    fake.fail.append(("POST", "/pages", 429, {"Retry-After": "7"}))
    (pushed, postponed, failed), _ = run(fake, docs)
    assert (pushed, postponed, failed) == (1, 0, 0)
    assert 7 in fake.sleeps
    assert fake.live_titles() == ["2026-11-27 (금) Test Topic"]


def test_truncated_or_old_pages_are_postponed():
    docs = make_docs({
        "2026-11-27": make_page(tail=False),               # 꼬리(성과 지표)가 잘린 페이지
        "2026-11-28": make_page(turns=0),                  # 화자 구분이 없는 옛 형식
    })
    fake = FakeNotion()
    (pushed, postponed, failed), logs = run(fake, docs)
    assert (pushed, postponed, failed) == (0, 2, 0), logs
    assert fake.live_titles() == [] and all(c[0] == "GET" for c in fake.calls)


def test_second_lesson_same_day_and_since():
    docs = make_docs({"2026-11-25": make_page(), "2026-11-27": make_page(), "2026-11-27-2": make_page()},
                     topics={"2026-11-27-2": "Second"})
    assert pn.candidates(docs, "2026-11-26") == ["2026-11-27", "2026-11-27-2"], "SINCE 이전은 올리지 않는다"
    fake = FakeNotion()
    (pushed, postponed, failed), _ = run(fake, docs)
    assert (pushed, postponed, failed) == (2, 0, 0)
    assert fake.live_titles() == ["2026-11-27 (금) Test Topic", "2026-11-27 (금) #2 Second"]
    (pushed, _, _), _ = run(fake, docs)
    assert pushed == 0


def test_no_token_skips_quietly():
    old = os.environ.pop("NOTION_TOKEN", None)
    real = pn.Notion
    pn.Notion = lambda *a, **k: (_ for _ in ()).throw(AssertionError("토큰이 없으면 노션에 붙으면 안 된다"))
    try:
        assert pn.main([]) == 0
    finally:
        pn.Notion = real
        if old is not None:
            os.environ["NOTION_TOKEN"] = old


def test_real_page_if_present():
    """저장소의 실제 복습 페이지도 빠짐없이 바뀌는지 (파일이 없으면 건너뜀)."""
    if not os.path.exists(os.path.join(pn.DOCS, "2026-11-26.html")):
        print("   (docs/2026-11-26.html 없음 — 건너뜀)")
        return
    title, blocks = pn.build_lesson("2026-11-26")
    out = pn.to_notion(blocks)
    texts = [plain(b) for b in out]
    assert title.startswith("2026-11-26 (목)"), title
    assert sum(1 for t in texts if t.startswith(("Student:", "Tutor:"))) > 50
    assert any(b["type"] == "table" for b in out)
    assert any("유창성 점수" in t for t in texts), "피드백 꼬리까지 들어와야 한다"
    assert texts[-1].startswith(("Student:", "Tutor:")), "전사 마지막 턴에서 끝나야 한다"
    fake = FakeNotion()
    client(fake).create_page(PARENT, "x", out[:100])       # 가짜 서버의 제한 검사를 통과해야 한다
    client(fake).append("page-1", out[100:200])


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"✅ {t.__name__}")
    print(f"\n{len(tests)}개 통과")

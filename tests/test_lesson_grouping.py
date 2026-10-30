#!/usr/bin/env python3
"""
나뉜 녹음 묶기 · 놓친 수업 재시도 · 페이지 이름 검사 / tests for lesson grouping and retry (2026-10-30).

실제로 있었던 경우로 검사한다: 10/08(33초 + 21분), 10/13(4분 + 2분), 8/05(21분 + 7초),
8/19(07:30 · 08:00 따로 두 수업), 8/17(08:00 · 09:01 · 17:00 세 수업), FolderSync 사본, 9/01(7일 밖).
실행 / run:  python3 tests/test_lesson_grouping.py   (pytest 불필요, 네트워크 미사용)
"""
import os
import sys
import tempfile
from datetime import datetime

for key in ("GOOGLE_CREDENTIALS", "GROQ_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.setdefault(key, "x")
os.environ["DRIVE_FOLDER_ID"] = "INBOX"
os.environ["DRIVE_DONE_FOLDER_ID"] = "DONE"
os.environ.pop("NOTIFY", None)
os.environ.pop("LESSON_DATES", None)
os.environ.pop("TARGET_DATE", None)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import process_lesson as pl  # noqa: E402

KST = pl.KST
MB_MIN = pl.AUDIO_BYTES_PER_SEC * 60  # 1분 녹음 크기


def name(stamp):
    return f"전화영어_025180304_{stamp}.m4a"


def f(fid, stamp, minutes):
    return {"id": fid, "name": name(stamp), "size": str(int(minutes * MB_MIN)), "createdTime": "2026-10-30T00:00:00Z"}


class _Call:
    def __init__(self, v):
        self.v = v

    def execute(self):
        return self.v


class FakeDrive:
    """폴더별 녹음 목록을 흉내 낸다. 수신 폴더는 두 쪽으로 나눠 돌려준다(쪽 넘김 검사)."""

    def __init__(self, inbox, done):
        self.folders = {"INBOX": inbox, "DONE": done}

    def files(self):
        return self

    def list(self, q="", pageToken=None, **_):
        folder = "INBOX" if "'INBOX' in parents" in q else "DONE"
        files = self.folders[folder]
        if folder == "INBOX" and len(files) > 1:
            half = len(files) // 2
            if pageToken is None:
                return _Call({"files": files[:half], "nextPageToken": "p2"})
            return _Call({"files": files[half:]})
        return _Call({"files": files})


def rec(stamp, minutes, processed=False, folder="done", fid=None):
    return {"id": fid or stamp, "name": name(stamp), "size": int(minutes * MB_MIN), "folder": folder,
            "start": pl.recording_start(name(stamp)), "processed": processed}


def main():
    failures = []

    def check(label, cond):
        print(("PASS " if cond else "FAIL ") + label)
        if not cond:
            failures.append(label)

    # 1) 파일명 → 녹음 시각
    check("시각 읽기", pl.recording_start(name("20261008080106")) == datetime(2026, 10, 8, 8, 1, 6, tzinfo=KST))
    check("시각 없는 이름", pl.recording_start("통화녹음.m4a") is None)

    # 2) 이어짐 기준 묶기 — 실제 사례
    def groups(*recs):
        return [[p["name"][-10:-4] for p in g] for g in pl.group_into_lessons(list(recs))]
    check("10/08 33초+21분 = 한 수업", groups(rec("20261008080016", 0.55), rec("20261008080106", 21)) == [["080016", "080106"]])
    check("10/13 4분+2분 = 한 수업", groups(rec("20261013080034", 4.2), rec("20261013080518", 2)) == [["080034", "080518"]])
    check("8/05 21분+끝난 뒤 7초 = 한 수업", groups(rec("20260805080018", 20), rec("20260805082017", 0.1)) == [["080018", "082017"]])
    check("8/19 07:30·08:00 = 두 수업", groups(rec("20260819073018", 21), rec("20260819080014", 20)) == [["073018"], ["080014"]])
    check("8/17 08:00·09:01·17:00 = 세 수업",
          len(pl.group_into_lessons([rec("20260817080037", 20), rec("20260817090103", 21), rec("20260817170028", 21)])) == 3)
    check("다른 날은 안 묶임", len(pl.group_into_lessons([rec("20261027235900", 5), rec("20261028000100", 5)])) == 2)

    # 3) 평소 모드 — 최근 7일의 처리 안 된 녹음 + 그 날 이미 처리된 조각
    tmp = tempfile.mkdtemp()
    pl.PROCESSED_FILE = os.path.join(tmp, "processed.txt")
    with open(pl.PROCESSED_FILE, "w", encoding="utf-8") as fh:
        fh.write(f"D29|{name('20261029080018')}\nD28|{name('20261028080014')}\n")
    inbox = [
        f("N30", "20261030080012", 21),          # 오늘 새 수업
        f("COPY29", "20261029080018", 21),       # FolderSync 사본 (처리된 이름)
        f("LATE28", "20261028080505", 3),        # 늦게 올라온 10/28 뒷조각
        f("OLD0901", "20260901080029", 21),      # 7일 밖 → 평소엔 안 건드림
    ]
    done = [f("D29", "20261029080018", 21), f("D28", "20261028080014", 4)]
    drive = FakeDrive(inbox, done)
    found = pl.find_lesson_recordings(drive, now=datetime(2026, 10, 30, 13, 30, tzinfo=KST))
    got = [(r["name"][-18:-4], r["folder"], r["processed"]) for r in found]
    check("평소: 10/28 두 조각 + 10/30, 사본·7일 밖 제외",
          got == [("20261028080014", "done", True), ("20261028080505", "inbox", False), ("20261030080012", "inbox", False)])
    check("쪽 넘김: 수신 폴더 두 번째 쪽도 읽음", any(r["id"] == "LATE28" for r in found))
    lessons = pl.select_lessons(pl.group_into_lessons(found))
    check("평소: 오래된 수업부터, 10/28 은 두 조각 묶음",
          [[p["id"] for p in g] for g in lessons] == [["D28", "LATE28"], ["N30"]])
    # 밀린 8일(10/23~30) 중 오래된 3개부터 — 최근 것부터 고르면 10/23 이 다음 날 7일 창 밖으로 빠진다
    capped = pl.select_lessons([[rec(f"202610{d}080000", 20, fid=str(d))] for d in range(23, 31)])
    check(f"평소: 한 번에 최대 {pl.MAX_LESSONS_PER_RUN}수업, 오래된 것부터",
          [g[0]["id"] for g in capped] == ["23", "24", "25"])

    # 4) 다시 만들기 모드 — 지정 날짜 전부, 이미 제대로 처리된 단일 수업은 제외
    with open(pl.PROCESSED_FILE, "w", encoding="utf-8") as fh:
        fh.write(f"D0901X|{name('20260817090103')}\nA|{name('20261008080016')}\nB|{name('20261008080106')}\n")
    drive = FakeDrive(
        [f("S0800", "20260817080037", 20), f("S1700", "20260817170028", 21), f("C1008", "20261008080106", 21)],
        [f("D0901X", "20260817090103", 21), f("A", "20261008080016", 0.55), f("B", "20261008080106", 21)],
    )
    found = pl.find_lesson_recordings(drive, lesson_dates=["2026-08-17", "2026-10-08"])
    picked = pl.select_lessons(pl.group_into_lessons(found), dates_mode=True)
    check("다시 만들기: 8/17 새 두 수업 + 10/08 묶음, 8/17 09:01 은 그대로",
          [[p["id"] for p in g] for g in picked] == [["S0800"], ["S1700"], ["A", "B"]])
    check("같은 이름이면 처리 기록의 원본을 씀", [p["folder"] for p in picked[2]] == ["done", "done"])

    # 5) 조각 이어 붙이기 — 뒤 조각 시각은 앞 조각 길이만큼 민다
    text, dur, segs = pl.join_transcripts([
        ("Hello Joey.", 33.0, [{"start": 0.0, "end": 2.0, "text": "Hello Joey."}]),
        (" Sorry, connection.", 1200.0, [{"start": 1.0, "end": 3.5, "text": "Sorry"}, None]),
    ])
    check("이어 붙이기: 글·길이", text == "Hello Joey.\nSorry, connection." and dur == 1233.0)
    check("이어 붙이기: 구간 시각 밀기", [s["start"] for s in segs] == [0.0, 34.0] and segs[1]["end"] == 36.5)

    # 6) 페이지 이름 — 같은 수업이면 덮어쓰기, 다른 수업이면 -2
    docs = os.path.join(tmp, "docs")
    os.makedirs(docs)
    with open(os.path.join(docs, "2026-10-08.html"), "w", encoding="utf-8") as fh:
        fh.write(f"<span>🎙 {name('20261008080016')}</span>")
    with open(os.path.join(docs, "2026-08-17.html"), "w", encoding="utf-8") as fh:
        fh.write(f"<span>🎙 {name('20260817090103')}</span>")
    d = lambda s: datetime.strptime(s, "%Y-%m-%d")  # noqa: E731
    check("페이지: 조각 페이지를 묶음으로 덮어씀",
          pl.choose_page_slug(docs, d("2026-10-08"), [name("20261008080016"), name("20261008080106")]) == "2026-10-08")
    check("페이지: 같은 날 다른 수업은 -2", pl.choose_page_slug(docs, d("2026-08-17"), [name("20260817080037")]) == "2026-08-17-2")
    check("페이지: 없으면 날짜 그대로", pl.choose_page_slug(docs, d("2026-09-01"), [name("20260901080029")]) == "2026-09-01")

    # 7) 수업 처리 — 짧은 조각 / 페이지만 다시 만들기
    calls = {"moved": [], "saved": [], "commit": 0, "raw": [], "kakao": [], "email": 0, "deploy": []}
    lengths = {}
    pl.download_recording = lambda svc, fid, nm: os.path.join(tmp, fid + ".m4a")
    pl.transcribe_audio = lambda path: ("t " + os.path.basename(path), lengths[os.path.basename(path)[:-4]],
                                        [{"start": 0.0, "end": 1.0, "text": "t"}])
    pl.move_to_done_folder = lambda fid: calls["moved"].append(fid)
    pl.save_processed_id = lambda fid, nm="": calls["saved"].append(fid)
    pl.commit_processed_record = lambda: calls.__setitem__("commit", calls["commit"] + 1)
    pl.save_raw_transcript = lambda nm, fid, ld, t, du, sg, **_: calls["raw"].append((fid, sg[0]["start"]))
    pl.notify_kakao = lambda text, link=None: calls["kakao"].append(text)
    pl.send_email = lambda *a, **k: calls.__setitem__("email", calls["email"] + 1)

    lengths.update({"FRAG": 60.0})
    url = pl.process_lesson_group(None, [rec("20260602080105", 1, folder="inbox", fid="FRAG")], notify=True)
    check("짧은 조각: 피드백 없음 + 기록·이동 + 알림", url is None and calls["saved"] == ["FRAG"]
          and calls["moved"] == ["FRAG"] and len(calls["kakao"]) == 1 and calls["email"] == 0)

    for k in calls:
        calls[k] = [] if isinstance(calls[k], list) else 0
    lengths.update({"A": 33.0, "B": 1200.0})
    seen = {}
    pl.clean_transcript = lambda raw, segs: (seen.__setitem__("raw", raw), seen.__setitem__("segs", segs), raw)[2]
    pl.verify_speaker_labels = lambda t: t
    pl.load_metadata = lambda d: {}
    pl.generate_feedback = lambda t, recent_categories=None: "feedback"
    pl.review_feedback = lambda t, fb: fb
    pl.extract_metadata = lambda fb: {"target_grammar": "x"}
    pl.save_metadata = lambda d, slug, meta: seen.__setitem__("meta_slug", slug)
    pl.generate_review_page = lambda t, fb, shown, du, ds: seen.update(shown=shown, dur=du) or "<html>"
    pl.deploy_review_page = lambda page, ds, ld, slug=None: calls["deploy"].append(slug) or f"https://x/{slug}.html"
    cwd = os.getcwd()
    os.chdir(tmp)  # choose_page_slug 는 docs/ 를 본다 → 위에서 만든 임시 docs
    try:
        url = pl.process_lesson_group(None, [rec("20261008080016", 0.55, processed=True, fid="A"),
                                             rec("20261008080106", 21, processed=True, fid="B")], notify=False)
    finally:
        os.chdir(cwd)
    check("다시 만들기: 같은 페이지에 묶음으로", calls["deploy"] == ["2026-10-08"] and seen["meta_slug"] == "2026-10-08"
          and url.endswith("2026-10-08.html"))
    check("다시 만들기: 두 조각 원문·길이 합침", seen["raw"].count("\n") == 1 and seen["dur"] == 1233.0
          and seen["shown"].endswith("외 1개"))
    check("다시 만들기: 보정에 넘긴 구간 시각이 이어짐", [s["start"] for s in seen["segs"]] == [0.0, 33.0])
    check("다시 만들기: 메일·알림 없음", calls["email"] == 0 and calls["kakao"] == [])
    check("다시 만들기: 이미 처리된 조각은 다시 기록·이동 안 함", calls["saved"] == [] and calls["moved"] == [] and calls["commit"] == 0)
    check("다시 만들기: 원본 보관은 조각마다 원래 시각으로", calls["raw"] == [("A", 0.0), ("B", 0.0)])

    # 8) 환경변수 해석
    os.environ["LESSON_DATES"] = "2026-08-05, 2026-09-01"
    check("날짜 목록 읽기", pl._lesson_dates_from_env() == ["2026-08-05", "2026-09-01"])
    os.environ["LESSON_DATES"] = "2026/08/05"
    try:
        pl._lesson_dates_from_env()
        check("날짜 형식 오류는 종료", False)
    except SystemExit:
        check("날짜 형식 오류는 종료", True)
    os.environ.pop("LESSON_DATES")
    check("알림: 평소 기본 보냄", pl._notify_from_env(False) is True)
    check("알림: 다시 만들기 기본 안 보냄", pl._notify_from_env(True) is False)
    os.environ["NOTIFY"] = "yes"
    check("알림: yes 가 우선", pl._notify_from_env(True) is True)
    os.environ["NOTIFY"] = "auto"
    check("알림: auto 는 모드 따라", pl._notify_from_env(True) is False)
    os.environ.pop("NOTIFY")

    print(f"\n{'ALL PASS' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

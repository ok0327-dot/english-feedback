#!/usr/bin/env python3
"""
주간 라디오 오디오(TTS) 검사 / tests for scripts/build_radio_audio.py (2026-11-19 TTS 모델 3.8 이전).

검사 내용 / what is checked:
  - 기본 모델 = gemini-3.8-flash-tts (3.1-flash-tts-preview 는 2026-12-18 이후 종료 예정), 대체 = lite
  - TTS 호출 주소에 넘긴 모델이 그대로 들어간다
  - 429 '하루 한도(PerDay)' → 재시도 없이 바로 DailyQuotaExceeded(한도 숫자 포함) / 분당 429 → 재시도
  - 대체 단계: 기본 모델이 중간에 실패하면 대체 모델로 '처음부터' 다시 → 한 회차에 두 모델 소리가 섞이지 않음
  - episodes.json 에 실제로 쓴 모델 기록 · 모든 Gemini 모델 실패 + 폴백 금지면 건너뜀
  - 샘플 모드: 지정 구간만 모델마다 합성, 한 모델 실패해도 계속, episodes.json·docs/radio 는 안 건드림
  - audio_stats: 길이·음량·무음 지표가 합성 신호에서 기대값
실행 / run:  python3 tests/test_radio_audio.py   (pytest 불필요, 네트워크 미사용)
"""
import array
import base64
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import build_radio_audio as A  # noqa: E402

failures = []


def check(name, ok):
    print(("  ✅ " if ok else "  ❌ ") + name)
    if not ok:
        failures.append(name)


class FakeResp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text or json.dumps(payload or {})

    def json(self):
        return self._payload


def audio_payload(pcm=b"\x01\x00" * 8, rate=24000):
    return {"candidates": [{"content": {"parts": [{"inlineData": {
        "mimeType": f"audio/L16;codec=pcm;rate={rate}", "data": base64.b64encode(pcm).decode()}}]}}]}


def write_radio(td, n):
    lines = [f"{'민지' if i % 2 else '알렉스'}|{'ko' if i % 5 == 0 else 'en'}|Line number {i}." for i in range(n)]
    fp = os.path.join(td, "radio.html")
    open(fp, "w", encoding="utf-8").write(
        '<html><body>2026-W46<pre id="radio-src" hidden>' + "\n".join(lines) + "</pre></body></html>")
    return fp, [tuple(x.split("|", 2)) for x in lines]


def main():
    real_post, real_sleep = A.requests.post, A.time.sleep
    sleeps = []
    A.time.sleep = lambda s: sleeps.append(s)
    A.GEMINI_KEY = "test-key"
    try:
        # 1) 기본 모델
        print("1) 기본 모델")
        if not (os.environ.get("GEMINI_TTS_MODEL") or "").strip():
            check("기본 = gemini-3.8-flash-tts", A.TTS_MODEL == "gemini-3.8-flash-tts")
        if not (os.environ.get("GEMINI_TTS_FALLBACK_MODELS") or "").strip():
            check("대체 기본 = gemini-3.8-flash-lite-tts", A.TTS_FALLBACK_MODELS == ["gemini-3.8-flash-lite-tts"])
        check("종료 예정 모델(3.1 preview)은 기본/대체에 없음",
              all("3.1-flash-tts-preview" not in m for m in [A.TTS_MODEL] + A.TTS_FALLBACK_MODELS))

        # 2) 호출 주소에 모델이 들어간다
        print("2) 호출 주소")
        seen = {}

        def post_ok(url, **kw):
            seen["url"] = url
            seen["speakers"] = [c["speaker"] for c in kw["json"]["generationConfig"]["speechConfig"]
                                ["multiSpeakerVoiceConfig"]["speakerVoiceConfigs"]]
            return FakeResp(200, audio_payload())
        A.requests.post = post_ok
        cfgs = [{"speaker": "Minji", "voiceConfig": {}}, {"speaker": "Alex", "voiceConfig": {}}]
        pcm, rate = A._tts_chunk([("민지", "en", "Hi.")], cfgs, "m-test")
        check("주소 = models/m-test:generateContent", seen["url"].endswith("/models/m-test:generateContent"))
        check("PCM·rate 복원", pcm == b"\x01\x00" * 8 and rate == 24000)
        A._tts_chunk([("민지", "en", "Hi.")], cfgs)
        check("모델 생략 시 기본 모델 주소", seen["url"].endswith(f"/models/{A.TTS_MODEL}:generateContent"))

        # 3) 하루 한도 429 → 재시도 없음 / 분당 429 → 재시도
        print("3) 429 처리")
        calls = []
        day_body = ('{"error":{"code":429,"message":"You exceeded your current quota. * Quota exceeded for metric: '
                    'generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 10, model: x",'
                    '"details":[{"violations":[{"quotaId":"GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}')
        A.requests.post = lambda url, **kw: calls.append(url) or FakeResp(429, text=day_body)
        sleeps.clear()
        try:
            A._tts_chunk_retry([("민지", "en", "Hi.")], cfgs, "m-day")
            check("하루 한도 → DailyQuotaExceeded", False)
        except A.DailyQuotaExceeded as e:
            check("하루 한도 → DailyQuotaExceeded(한도 숫자 포함)", "하루 10회" in str(e) and "m-day" in str(e))
        check("하루 한도는 재시도 안 함(호출 1번·대기 0)", len(calls) == 1 and not sleeps)
        calls.clear()
        minute_body = '{"error":{"code":429,"quotaId":"GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}}'
        A.requests.post = lambda url, **kw: calls.append(url) or FakeResp(429, text=minute_body)
        try:
            A._tts_chunk_retry([("민지", "en", "Hi.")], cfgs, "m-min", tries=3)
        except A.DailyQuotaExceeded:
            check("분당 429 는 일일 한도로 오인하지 않음", False)
        except RuntimeError:
            pass
        check("분당 429 는 재시도(3번 호출)", len(calls) == 3)

        # 4) 대체 단계: 한 회차 = 한 모델
        print("4) 대체 모델 단계")
        real_chunk = A._tts_chunk
        old_main, old_fb, old_chunk_lines = A.TTS_MODEL, A.TTS_FALLBACK_MODELS, A.CHUNK_LINES
        A.TTS_MODEL, A.TTS_FALLBACK_MODELS, A.CHUNK_LINES = "main-m", ["lite-m"], 2
        order = []

        def fake_chunk(chunk, cfgs, model=None):
            order.append(model)
            if model == "main-m" and order.count("main-m") == 2:
                raise A.DailyQuotaExceeded("하루 한도")
            return (b"M" if model == "main-m" else b"L") * 4, 24000
        A._tts_chunk = fake_chunk
        lines6 = [("민지", "en", f"L{i}") for i in range(6)]
        pcm, rate, used = A.gemini_tts_ladder(lines6)
        check("기본 모델 실패 → 대체 모델로 완성", used == "lite-m")
        check("결과에 기본 모델 소리 없음(섞지 않음)", b"M" not in pcm and pcm.count(b"L") == 12)
        check("대체 모델은 처음 청크부터 다시(3청크)", order == ["main-m", "main-m", "lite-m", "lite-m", "lite-m"])
        A._tts_chunk = lambda chunk, cfgs, model=None: (_ for _ in ()).throw(RuntimeError(f"down {model}"))
        try:
            A.gemini_tts_ladder(lines6)
            check("전부 실패면 예외", False)
        except RuntimeError as e:
            check("전부 실패면 마지막 모델 예외 전파", "lite-m" in str(e))

        # 5) build_episode: episodes.json 에 쓴 모델 기록 / 폴백 금지면 건너뜀
        print("5) 에피소드 기록")
        with tempfile.TemporaryDirectory() as td:
            fp, _ = write_radio(td, 6)
            old_dir, old_mp3 = A.RADIO_DIR, A.pcm_to_mp3
            A.RADIO_DIR = os.path.join(td, "radio")
            os.makedirs(A.RADIO_DIR)
            A.pcm_to_mp3 = lambda pcm, rate, out: open(out, "wb").write(b"mp3")
            A._tts_chunk = fake_chunk
            order.clear()
            try:
                r = A.build_episode(fp, allow_fallback=False)
                eps = json.load(open(os.path.join(A.RADIO_DIR, "episodes.json"), encoding="utf-8"))
                check("회차 생성", r == ("2026-W46", "gemini", 6))
                check("episodes.json 에 실제 모델(lite-m) 기록", eps[0].get("model") == "lite-m" and eps[0]["engine"] == "gemini")
                A._tts_chunk = lambda chunk, cfgs, model=None: (_ for _ in ()).throw(RuntimeError("down"))
                check("모든 Gemini 실패 + 폴백 금지 → None", A.build_episode(fp, allow_fallback=False) is None)
            finally:
                A.RADIO_DIR, A.pcm_to_mp3 = old_dir, old_mp3
        A._tts_chunk = real_chunk
        A.TTS_MODEL, A.TTS_FALLBACK_MODELS, A.CHUNK_LINES = old_main, old_fb, old_chunk_lines

        # 6) audio_stats: 1초 무음 + 1초 사각파(진폭 16384)
        print("6) audio_stats")
        rate = 24000
        a = array.array("h", [0] * rate + [16384 if (i // 20) % 2 else -16384 for i in range(rate)])
        if sys.byteorder == "big":
            a.byteswap()
        st = A.audio_stats(a.tobytes(), rate)
        check("길이 2.0초", st["sec"] == 2.0)
        check("무음 50%·최장 무음 1.0초", st["silence_pct"] == 50.0 and st["longest_silence"] == 1.0)
        check("peak -6.0 dBFS · RMS -9.0 dBFS", st["peak_dbfs"] == -6.0 and st["rms_dbfs"] == -9.0)
        check("빈 PCM 도 안전", A.audio_stats(b"", rate)["sec"] == 0.0)

        # 7) 샘플 모드: 구간·모델별 파일·실패 격리·docs 안 건드림
        print("7) 샘플 모드")
        with tempfile.TemporaryDirectory() as td:
            fp, lines = write_radio(td, 30)
            out_dir = os.path.join(td, "samples")
            got = []

            def fake_tts(window, model=None):
                got.append((model, list(window)))
                if model == "b-fail":
                    raise RuntimeError("Gemini TTS 404 [b-fail]: not found")
                return b"\x00\x10" * 24000, 24000
            real_tts, old_mp3, old_dir = A.gemini_tts, A.pcm_to_mp3, A.RADIO_DIR
            A.gemini_tts, A.RADIO_DIR = fake_tts, os.path.join(td, "radio-should-not-exist")
            A.pcm_to_mp3 = lambda pcm, rate, out: open(out, "wb").write(b"mp3")
            try:
                res = A.build_samples(fp, ["a", "b-fail", "c/x"], 10, 5, out_dir)
            finally:
                A.gemini_tts, A.pcm_to_mp3 = real_tts, old_mp3
            check("모델마다 같은 구간(5~14줄)", all(w == lines[5:15] for _, w in got) and [m for m, _ in got] == ["a", "b-fail", "c/x"])
            check("실패 모델은 오류로 기록·나머지 계속", res[1][1] is None and "404" in res[1][2] and res[2][1] is not None)
            check("모델별 파일(이름 안전 처리)", sorted(os.listdir(out_dir)) == ["sample-a.mp3", "sample-c_x.mp3"])
            check("지표: 길이 1.0초·줄당 0.1초", res[0][1]["sec"] == 1.0 and res[0][1]["sec_per_line"] == 0.1)
            check("docs/radio·episodes.json 안 건드림", not os.path.exists(A.RADIO_DIR))
            A.RADIO_DIR = old_dir

        # 8) CLI --sample: 전부 실패면 종료 코드 ≠ 0
        print("8) CLI")
        with tempfile.TemporaryDirectory() as td:
            fp, _ = write_radio(td, 5)
            old_docs, real_tts = A.DOCS, A.gemini_tts
            A.DOCS = td
            A.gemini_tts = lambda window, model=None: (_ for _ in ()).throw(RuntimeError("down"))
            old_argv = sys.argv
            sys.argv = ["x", "--sample", "3", "--models", "a,b", "--out-dir", os.path.join(td, "s")]
            try:
                A.main()
                check("전부 실패 → SystemExit", False)
            except SystemExit as e:
                check("전부 실패 → SystemExit(메시지)", "모든 모델 샘플 실패" in str(e.code))
            finally:
                sys.argv, A.DOCS, A.gemini_tts = old_argv, old_docs, real_tts
    finally:
        A.requests.post, A.time.sleep = real_post, real_sleep

    print(f"\n{'ALL PASS' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

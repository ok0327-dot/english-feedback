#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎧 주간 라디오 오디오(MP3) 생성기 / Weekly radio audio.

docs/radio.html 의 <pre id="radio-src"> 대본(진행자|lang|문장)을 읽어
실제 음성 MP3를 만든다:
  1순위) Gemini 멀티스피커 TTS(두 진행자 다른 목소리, 한/영 자동). PCM→MP3.
  폴백)  gTTS(무료, 언어별 합성 후 이어붙임) — Gemini 실패/쿼터 시에도 에피소드 보장.
→ docs/radio/ep-YYYY-Www.mp3 저장 + docs/radio/episodes.json 갱신.

자격증명: GEMINI_API_KEY(env, 기존 시크릿 재사용). 모델: GEMINI_TTS_MODEL(기본 2.5-flash-preview-tts).
의존성: requests, gTTS, pydub + ffmpeg.

CLI:  python3 scripts/build_radio_audio.py                # 현재 주(docs/radio.html)
      python3 scripts/build_radio_audio.py --week 2026-W25  # 아카이브 특정 주
      python3 scripts/build_radio_audio.py --backfill       # MP3 없는 아카이브 전 주차 (Gemini 전용, 실패 주는 건너뜀)
"""
import os, sys, re, html, json, base64, wave, io, glob, time, subprocess, tempfile, datetime
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
RADIO_DIR = os.path.join(DOCS, "radio")
KST = datetime.timezone(datetime.timedelta(hours=9))

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
# 빈 문자열(env는 설정됐지만 값이 없음 — 워크플로우 dispatch 기본값)도 기본 모델로 처리
TTS_MODEL = (os.environ.get("GEMINI_TTS_MODEL") or "").strip() or "gemini-3.1-flash-tts-preview"
# 진행자 → (TTS용 ASCII 라벨, Gemini 프리빌트 보이스)
SPEAKERS = {"민지": ("Minji", "Kore"), "알렉스": ("Alex", "Puck")}


def parse_radio_html(path=None):
    """radio.html 또는 아카이브(radio-YYYY-Www.html)에서 (week, 대사 lines) 추출."""
    path = path or os.path.join(DOCS, "radio.html")
    t = open(path, encoding="utf-8").read()
    m = re.search(r'<pre id="radio-src"[^>]*>(.*?)</pre>', t, re.S)
    if not m:
        sys.exit(f"❌ {os.path.basename(path)} 에서 <pre id=\"radio-src\"> 를 찾지 못함")
    raw = html.unescape(m.group(1)).strip()
    lines = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        parts = ln.split("|", 2)
        if len(parts) == 3 and parts[0] and parts[1]:
            lines.append((parts[0], parts[1], parts[2]))
    mw = re.search(r"(20\d\d-W\d\d)", os.path.basename(path)) or re.search(r"(20\d\d-W\d\d)", t)
    week = mw.group(1) if mw else "latest"
    return week, lines


# 한 TTS 호출당 대사 줄 수. 무료 티어 일일 한도(10회/일/모델) 안에 에피소드 하나(≤200줄)가
# 들어가도록 20줄(=6~10청크/에피소드). 청크가 줄면 이음새도 줄어 품질에도 유리.
CHUNK_LINES = int(os.environ.get("TTS_CHUNK_LINES", "20"))


def _tts_chunk(chunk, cfgs):
    """대사 청크 하나 → (pcm_bytes, rate). Gemini 멀티스피커 TTS 단일 호출."""
    transcript = ("Read this radio dialogue as a warm, lively two-host learning podcast. "
                  "Speak naturally and expressively, with genuine back-and-forth energy, "
                  "at a relaxed and clear pace for an English learner (A2-B1 level). "
                  "Mostly English, with occasional Korean lines spoken natively:\n" +
                  "\n".join(f"{SPEAKERS.get(sp, (sp, 'Kore'))[0]}: {txt}" for sp, _, txt in chunk))
    body = {
        "contents": [{"parts": [{"text": transcript}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": cfgs}},
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{TTS_MODEL}:generateContent"
    r = requests.post(url, headers={"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"},
                      json=body, timeout=240)
    if r.status_code != 200:
        raise RuntimeError(f"Gemini TTS {r.status_code}: {re.sub(chr(10), ' ', r.text)[:300]}")
    j = r.json()
    parts = (j.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    for part in parts:
        inl = part.get("inlineData") or part.get("inline_data")
        if inl and inl.get("data"):
            rate = 24000
            mm = re.search(r"rate=(\d+)", inl.get("mimeType") or inl.get("mime_type") or "")
            if mm:
                rate = int(mm.group(1))
            return base64.b64decode(inl["data"]), rate
    raise RuntimeError("Gemini TTS 응답에 오디오(inlineData) 없음")


TTS_PACE_SEC = float(os.environ.get("TTS_PACE_SEC", "12"))  # 청크 사이 최소 간격(RPM 한도 회피)


def _tts_chunk_retry(chunk, cfgs, tries=4):
    """청크 TTS + 재시도(429 속도제한·일시 오류에 backoff). 실패 시 마지막 예외 전파."""
    for attempt in range(tries):
        try:
            return _tts_chunk(chunk, cfgs)
        except Exception as e:
            if attempt == tries - 1:
                raise
            wait = 30 * (attempt + 1)
            print(f"  ⚠️ TTS 재시도 {attempt + 1}/{tries - 1} ({str(e)[:160]}) — {wait}s 대기")
            time.sleep(wait)


def gemini_tts(lines):
    """긴 대본을 청크로 나눠 TTS 후 PCM 이어붙임 → (pcm_bytes, rate).
    청크 사이 300ms 무음을 넣어 이음새를 자연스럽게 한다."""
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY 미설정")
    order, seen = [], set()
    for sp, _, _ in lines:
        if sp not in seen:
            seen.add(sp); order.append(sp)
    cfgs = [{"speaker": SPEAKERS.get(sp, (sp, "Kore"))[0],
             "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": SPEAKERS.get(sp, (sp, "Kore"))[1]}}}
            for sp in order[:2]]
    pcm_parts, rate = [], 24000
    n = (len(lines) + CHUNK_LINES - 1) // CHUNK_LINES
    for i in range(0, len(lines), CHUNK_LINES):
        if i:
            time.sleep(TTS_PACE_SEC)  # 속도 제한(RPM) 회피용 페이싱
        pcm, rate = _tts_chunk_retry(lines[i:i + CHUNK_LINES], cfgs)
        pcm_parts.append(pcm)
        print(f"  …TTS 청크 {i // CHUNK_LINES + 1}/{n} ({len(pcm)//1024}KB)")
    gap = b"\x00\x00" * int(0.3 * rate)  # 300ms 무음(16-bit mono)
    return gap.join(pcm_parts), rate


def pcm_to_mp3(pcm, rate, out):
    """PCM(16-bit mono) → MP3(48k mono). ffmpeg 우선, 없으면 lameenc(순수 파이썬) 폴백."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            w = wave.open(tf, "wb")
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm); w.close()
            wavpath = tf.name
        subprocess.run(["ffmpeg", "-y", "-i", wavpath, "-ac", "1", "-codec:a", "libmp3lame", "-b:a", "48k", out],
                       check=True, capture_output=True)
        os.remove(wavpath)
    except FileNotFoundError:  # ffmpeg 없음 (로컬 실행 등)
        import lameenc
        enc = lameenc.Encoder()
        enc.set_bit_rate(48); enc.set_in_sample_rate(rate); enc.set_channels(1); enc.set_quality(2)
        data = enc.encode(pcm) + enc.flush()
        open(out, "wb").write(bytes(data))


def gtts_fallback(lines, out):
    """gTTS로 줄별 합성 후 이어붙여 MP3."""
    from gtts import gTTS
    from pydub import AudioSegment
    combined = AudioSegment.silent(duration=300)
    for sp, lang, txt in lines:
        if not txt.strip():
            continue
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
            gTTS(text=txt, lang=("ko" if lang == "ko" else "en")).save(tf.name)
            seg = AudioSegment.from_mp3(tf.name)
        combined += seg + AudioSegment.silent(duration=250)
        os.remove(tf.name)
    combined.export(out, format="mp3", bitrate="48k")


def update_episodes(week, engine, nlines):
    """episodes.json 에 항목 추가/교체(최신순) + 오래된 mp3 정리."""
    epf = os.path.join(RADIO_DIR, "episodes.json")
    eps = []
    if os.path.exists(epf):
        try:
            eps = json.load(open(epf, encoding="utf-8"))
        except Exception:
            eps = []
    eps = [e for e in eps if e.get("week") != week]
    eps.append({"week": week, "date": datetime.datetime.now(KST).strftime("%Y-%m-%d"),
                "file": f"ep-{week}.mp3", "engine": engine, "lines": nlines})
    eps.sort(key=lambda e: e.get("week", ""), reverse=True)

    KEEP = int(os.environ.get("RADIO_KEEP", "16"))
    keep_files = {e["file"] for e in eps[:KEEP]}
    eps = eps[:KEEP]
    for fn in os.listdir(RADIO_DIR):
        if fn.endswith(".mp3") and fn not in keep_files:
            try:
                os.remove(os.path.join(RADIO_DIR, fn))
                print(f"  🗑 오래된 에피소드 정리: {fn}")
            except OSError:
                pass
    json.dump(eps, open(epf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def build_episode(html_path, allow_fallback):
    """한 주차 페이지 → MP3. 성공 시 (week, engine, 줄수), 실패 시 None."""
    week, lines = parse_radio_html(html_path)
    if not lines:
        print(f"⚠️ {week}: 대본 라인 없음 — 건너뜀")
        return None
    out = os.path.join(RADIO_DIR, f"ep-{week}.mp3")
    engine = "gemini"
    try:
        pcm, rate = gemini_tts(lines)
        pcm_to_mp3(pcm, rate, out)
    except Exception as e:
        if not allow_fallback:
            print(f"⚠️ {week}: Gemini TTS 실패 ({str(e)[:80]}) — 폴백 없이 건너뜀")
            return None
        print(f"⚠️ Gemini TTS 실패 ({e}) → gTTS 폴백")
        engine = "gtts"
        gtts_fallback(lines, out)
    update_episodes(week, engine, len(lines))
    size_kb = os.path.getsize(out) // 1024
    print(f"✅ {engine} TTS · docs/radio/ep-{week}.mp3 · {size_kb}KB · {len(lines)}줄")
    return week, engine, len(lines)


def main():
    args = sys.argv[1:]
    os.makedirs(RADIO_DIR, exist_ok=True)
    targets = []  # (html_path, allow_fallback)
    if "--backfill" in args:
        # 아카이브 전 주차 중 MP3 없는 것만. 품질 보장 위해 gTTS 폴백 없이 Gemini 전용.
        for p in sorted(glob.glob(os.path.join(DOCS, "radio-20??-W??.html"))):
            wk = re.search(r"(20\d\d-W\d\d)", os.path.basename(p)).group(1)
            if not os.path.exists(os.path.join(RADIO_DIR, f"ep-{wk}.mp3")):
                targets.append((p, False))
        if not targets:
            print("백필 대상 없음 — 모든 아카이브에 MP3 존재"); return
        if "--limit" in args:  # 일일 무료 쿼터(10회/모델)에 맞춰 하루 N개 주차만
            targets = targets[:int(args[args.index("--limit") + 1])]
    elif "--week" in args:
        wk = args[args.index("--week") + 1]
        p = os.path.join(DOCS, f"radio-{wk}.html")
        targets.append((p if os.path.exists(p) else os.path.join(DOCS, "radio.html"), False))
    else:
        targets.append((os.path.join(DOCS, "radio.html"), True))  # 기존 동작(주간 자동)

    done, last = 0, None
    for html_path, allow_fb in targets:
        r = build_episode(html_path, allow_fb)
        if r:
            done += 1; last = r
    if not last:
        sys.exit("❌ 생성된 에피소드 없음")
    # 워크플로우 호환 출력(마지막 에피소드 기준)
    print(f"EPISODE_FILE=radio/ep-{last[0]}.mp3")
    print(f"EPISODE_WEEK={last[0]}")
    print(f"🏁 총 {done}/{len(targets)}개 에피소드 생성 완료")


if __name__ == "__main__":
    main()

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

CLI:  python3 scripts/build_radio_audio.py
"""
import os, sys, re, html, json, base64, wave, io, subprocess, tempfile, datetime
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
RADIO_DIR = os.path.join(DOCS, "radio")
KST = datetime.timezone(datetime.timedelta(hours=9))

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts").strip()
# 진행자 → (TTS용 ASCII 라벨, Gemini 프리빌트 보이스)
SPEAKERS = {"민지": ("Minji", "Kore"), "알렉스": ("Alex", "Puck")}


def parse_radio_html():
    path = os.path.join(DOCS, "radio.html")
    t = open(path, encoding="utf-8").read()
    m = re.search(r'<pre id="radio-src"[^>]*>(.*?)</pre>', t, re.S)
    if not m:
        sys.exit("❌ radio.html 에서 <pre id=\"radio-src\"> 를 찾지 못함")
    raw = html.unescape(m.group(1)).strip()
    lines = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        parts = ln.split("|", 2)
        if len(parts) == 3 and parts[0] and parts[1]:
            lines.append((parts[0], parts[1], parts[2]))
    mw = re.search(r"(20\d\d-W\d\d)", t)
    week = mw.group(1) if mw else "latest"
    return week, lines


CHUNK_LINES = 12   # 한 TTS 호출당 대사 줄 수(단일 호출 길이 한도 회피 → 긴 에피소드 가능)


def _tts_chunk(chunk, cfgs):
    """대사 청크 하나 → (pcm_bytes, rate). Gemini 멀티스피커 TTS 단일 호출."""
    transcript = ("TTS the following English radio dialogue naturally and expressively:\n" +
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
        raise RuntimeError(f"Gemini TTS {r.status_code}: {r.text[:200]}")
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


def gemini_tts(lines):
    """긴 대본을 청크로 나눠 TTS 후 PCM 이어붙임 → (pcm_bytes, rate)."""
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY 미설정")
    order, seen = [], set()
    for sp, _, _ in lines:
        if sp not in seen:
            seen.add(sp); order.append(sp)
    cfgs = [{"speaker": SPEAKERS.get(sp, (sp, "Kore"))[0],
             "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": SPEAKERS.get(sp, (sp, "Kore"))[1]}}}
            for sp in order[:2]]
    pcm_all, rate = b"", 24000
    n = (len(lines) + CHUNK_LINES - 1) // CHUNK_LINES
    for i in range(0, len(lines), CHUNK_LINES):
        pcm, rate = _tts_chunk(lines[i:i + CHUNK_LINES], cfgs)
        pcm_all += pcm
        print(f"  …TTS 청크 {i // CHUNK_LINES + 1}/{n} ({len(pcm)//1024}KB)")
    return pcm_all, rate


def pcm_to_mp3(pcm, rate, out):
    """PCM(16-bit mono) → WAV(stdlib) → ffmpeg → MP3(48k mono, 음성용 저용량)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        w = wave.open(tf, "wb")
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm); w.close()
        wavpath = tf.name
    subprocess.run(["ffmpeg", "-y", "-i", wavpath, "-ac", "1", "-codec:a", "libmp3lame", "-b:a", "48k", out],
                   check=True, capture_output=True)
    os.remove(wavpath)


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


def main():
    week, lines = parse_radio_html()
    if not lines:
        sys.exit("❌ 대본 라인 없음")
    os.makedirs(RADIO_DIR, exist_ok=True)
    out = os.path.join(RADIO_DIR, f"ep-{week}.mp3")
    engine = "gemini"
    try:
        pcm, rate = gemini_tts(lines)
        pcm_to_mp3(pcm, rate, out)
    except Exception as e:
        print(f"⚠️ Gemini TTS 실패 ({e}) → gTTS 폴백")
        engine = "gtts"
        gtts_fallback(lines, out)

    # episodes.json 갱신(같은 주는 교체, 최신순)
    epf = os.path.join(RADIO_DIR, "episodes.json")
    eps = []
    if os.path.exists(epf):
        try:
            eps = json.load(open(epf, encoding="utf-8"))
        except Exception:
            eps = []
    eps = [e for e in eps if e.get("week") != week]
    eps.append({"week": week, "date": datetime.datetime.now(KST).strftime("%Y-%m-%d"),
                "file": f"ep-{week}.mp3", "engine": engine, "lines": len(lines)})
    eps.sort(key=lambda e: e.get("week", ""), reverse=True)

    # 용량 관리: 최신 KEEP개만 보관, 오래된 mp3 삭제
    KEEP = int(os.environ.get("RADIO_KEEP", "8"))
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

    size_kb = os.path.getsize(out) // 1024
    print(f"EPISODE_FILE=radio/ep-{week}.mp3")
    print(f"EPISODE_WEEK={week}")
    print(f"✅ {engine} TTS · docs/radio/ep-{week}.mp3 · {size_kb}KB · {len(lines)}줄")


if __name__ == "__main__":
    main()

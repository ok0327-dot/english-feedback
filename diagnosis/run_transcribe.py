"""
V7 '귀' 실행기 — gemini-3.5-transcribe 가 녹음을 직접 듣고 받아쓰기 + 화자 구분 (DIAGNOSIS_PLAN 3절·6절).

- dry-run : 개인 정보가 없는 1초 합성음으로 업로드 → 받아쓰기 → 삭제 → 삭제 확인까지 미리 시험한다.
- run --go: 실제 녹음 5건. 사용자가 무료 등급 전송에 동의했다(2026-10-30). 녹음에는 튜터 목소리도 있다.
  올린 파일은 받아쓰기가 끝나는 즉시 지우고(48시간 자동 삭제를 기다리지 않음), 지운 것까지 확인해 기록한다.
  이미 보낸 데이터의 개선 활용·사람 검토는 되돌릴 수 없다 — 그래서 --go 없이는 돌지 않는다.
녹음 1건 ≈ 18.6MB 라 요청 본문에 바로 넣는 방식(20MB 제한)이 아니라 Files API 로 올린다.

실행: python3 -m diagnosis.run_transcribe dry-run
      python3 -m diagnosis.run_transcribe run --go
"""
import io
import json
import math
import os
import struct
import sys
import time
import wave
from datetime import datetime

import requests

from diagnosis.common import DIAG, INPUT, KST, ROOT, SAMPLES, atomic_write_json, manifest_add, out_path, require_frozen_items

API = "https://generativelanguage.googleapis.com"
MODEL = "gemini-3.5-transcribe"
LOG = os.path.join(DIAG, "upload_log.jsonl")
PROMPT = (
    "Transcribe this phone English lesson verbatim. Two speakers: a native-speaker tutor and a Korean learner. "
    "Label each turn by voice as 'Speaker A:' / 'Speaker B:' and start each turn with [mm:ss]. "
    "Write exactly what was said: keep grammar mistakes, wrong words, fillers (uh, um) and repetitions. "
    "Do not correct, summarize or omit anything. Mark unclear words as [unclear]."
)


def _key():
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if not k:
        try:
            from dotenv import dotenv_values
            k = (dotenv_values(os.path.join(ROOT, ".env")).get("GEMINI_API_KEY") or "").strip()
        except ImportError:
            pass
    if not k:
        raise SystemExit("❌ GEMINI_API_KEY 없음")
    return k


def _log(entry):
    os.makedirs(DIAG, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(entry, at=datetime.now(KST).isoformat(timespec="seconds")), ensure_ascii=False) + "\n")


def upload(data, mime, name, key):
    start = requests.post(f"{API}/upload/v1beta/files", timeout=60, headers={
        "x-goog-api-key": key, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(len(data)), "X-Goog-Upload-Header-Content-Type": mime,
        "Content-Type": "application/json"}, json={"file": {"display_name": name}})
    start.raise_for_status()
    url = start.headers["x-goog-upload-url"]
    done = requests.post(url, data=data, timeout=300, headers={
        "X-Goog-Upload-Command": "upload, finalize", "X-Goog-Upload-Offset": "0", "Content-Length": str(len(data))})
    done.raise_for_status()
    f = done.json()["file"]
    for _ in range(60):  # 처리 끝날 때까지 (오디오는 보통 몇 초)
        if f.get("state") in (None, "ACTIVE"):
            return f
        if f.get("state") == "FAILED":
            raise RuntimeError("Files API 처리 실패")
        time.sleep(2)
        f = requests.get(f"{API}/v1beta/{f['name']}", headers={"x-goog-api-key": key}, timeout=30).json()
    raise RuntimeError("Files API 처리 시간 초과")


def delete(name, key):
    """지우고, 정말 없어졌는지(404) 확인한다."""
    requests.delete(f"{API}/v1beta/{name}", headers={"x-goog-api-key": key}, timeout=30)
    gone = requests.get(f"{API}/v1beta/{name}", headers={"x-goog-api-key": key}, timeout=30).status_code in (403, 404)
    return gone


def transcribe(f, key, max_tokens=16384):
    body = {"contents": [{"parts": [{"file_data": {"mime_type": f["mimeType"], "file_uri": f["uri"]}},
                                    {"text": PROMPT}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.0}}
    r = requests.post(f"{API}/v1beta/models/{MODEL}:generateContent", json=body, timeout=600,
                      headers={"x-goog-api-key": key})
    if r.status_code != 200:
        raise RuntimeError(f"받아쓰기 오류 {r.status_code}: {r.text[:200]}")
    j = r.json()
    text = "".join(p.get("text", "") for c in j.get("candidates", []) for p in c.get("content", {}).get("parts", []))
    u = j.get("usageMetadata") or {}
    return text, {"in": u.get("promptTokenCount"), "out": u.get("candidatesTokenCount")}, \
        (j.get("candidates") or [{}])[0].get("finishReason")


def one(data, mime, label, key):
    f = upload(data, mime, label, key)
    _log({"event": "uploaded", "label": label, "file": f["name"], "bytes": len(data)})
    try:
        for attempt in range(3):  # 503(일시 과부하)·429 는 잠깐 뒤 다시 (같은 업로드 파일로)
            try:
                text, tokens, finish = transcribe(f, key)
                break
            except RuntimeError as e:
                if attempt == 2 or not any(c in str(e) for c in ("503", "429", "500")):
                    raise
                print(f"⏳ {label}: {str(e)[:60]} — {20 * (attempt + 1)}초 뒤 다시")
                time.sleep(20 * (attempt + 1))
    finally:
        gone = delete(f["name"], key)
        _log({"event": "deleted", "label": label, "file": f["name"], "confirmed_gone": gone})
        if not gone:
            print(f"⚠️ {label}: 업로드 파일 삭제를 확인하지 못함 ({f['name']}) — 48시간 뒤 자동 삭제")
    return text, tokens, finish, gone


def dry_run():
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
    w.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * i / 16000))) for i in range(16000)))
    w.close()
    text, tokens, finish, gone = one(buf.getvalue(), "audio/wav", "diag-dry-run-tone", _key())
    print(f"✅ 사전 시험: 업로드·받아쓰기({finish}, 토큰 {tokens})·삭제{'·삭제 확인' if gone else ' (확인 실패)'}")
    return gone


def run(go=False):
    if not go:
        raise SystemExit("❌ 실제 녹음은 --go 를 붙여야 보낸다 (무료 등급 전송은 되돌릴 수 없음)")
    require_frozen_items()
    key = _key()
    for date, fname in sorted(SAMPLES.items()):
        dest = out_path("V7ears", date)
        if os.path.exists(dest):
            continue
        path = os.path.join(INPUT, fname)
        data = open(path, "rb").read()
        t0 = time.time()
        text, tokens, finish, gone = one(data, "audio/mp4", f"diag-{date}", key)
        atomic_write_json(dest, {"date": date, "model": MODEL, "source_file": fname, "text": text, "tokens": tokens,
                                 "finish": finish, "upload_deleted": gone, "seconds": round(time.time() - t0)})
        manifest_add({"variant": "V7ears", "date": date, "status": "done", "model": MODEL, "tokens": tokens})
        print(f"✅ V7 귀 {date}: {len(text)}자, {finish}, 토큰 {tokens}, 업로드 삭제 {'확인' if gone else '미확인'}")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "dry-run":
        dry_run()
    elif cmd == "run":
        run(go="--go" in argv)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)

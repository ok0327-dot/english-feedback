"""
30줄 정답 표시 / 30-line human labels for M2 (speaker) and M5 (Whisper confidence) — DIAGNOSIS_PLAN 4절.

make  : 10/07 수업 Whisper 구간에서 30줄을 **변형판을 보기 전에** 고른다
        (화자 전환 후보 10 · 이름 호명·질문 10 · 무작위 10) → 바탕화면 '진단-라벨링' 폴더에 label.html + 녹음.
        모두 사용자 PC 안에서만 돈다 (어디에도 올리지 않음).
score : 다운로드 폴더의 labels-2026-10-07.json 으로 판별 화자 오배정(M2)과 신뢰도 점수 쓸모(M5, AUC) 계산.
실행: python3 -m diagnosis.label make | score
"""
import glob
import html
import json
import os
import random
import re
import shutil
import sys

from diagnosis.common import (ARCHIVE_NAME, DIAG, INPUT, OUT, SAMPLES, atomic_write_json, best_window, load_archive,
                              read_json, words)

DATE = "2026-10-07"
PICKS = os.path.join(DIAG, "label_lines.json")
NAMES = re.compile(r"\b(joey|bell|joanna|teacher)\b|\?", re.I)


def _out_dir():
    if os.environ.get("LABEL_DIR"):
        return os.environ["LABEL_DIR"]
    desks = sorted(glob.glob("/mnt/c/Users/*/Desktop"))
    desks = [d for d in desks if "/Public/" not in d and "/Default" not in d]
    return os.path.join(desks[0] if desks else DIAG, "진단-라벨링")


def select(segments, n_each=10, seed=1007):
    """세 갈래로 10줄씩. 너무 짧은 구간(두 단어 미만·1초 미만)은 뺀다. 같은 줄은 한 번만."""
    segs = [s for s in segments if isinstance(s, dict) and len(words(s.get("text"))) >= 2
            and (s.get("end", 0) - s.get("start", 0)) >= 1.0]
    rnd, chosen = random.Random(seed), {}
    prev_end = {id(s): (segments[i - 1].get("end", 0) if i else 0) for i, s in enumerate(segments) if isinstance(s, dict)}
    boundary = [s for s in segs if s.get("start", 0) - prev_end.get(id(s), 0) >= 1.5]
    named = [s for s in segs if NAMES.search(s.get("text") or "")]
    # 앞 갈래가 모자라면 무작위 갈래가 그만큼 더 채운다 (항상 n_each*3 줄)
    for k, (group, label) in enumerate(((boundary, "화자 전환 후보"), (named, "호명·질문"), (segs, "무작위"))):
        need = n_each * (k + 1) - len(chosen)
        pool = [s for s in group if s.get("id", s.get("start")) not in chosen]
        for s in rnd.sample(pool, max(0, min(need, len(pool)))):
            chosen[s.get("id", s.get("start"))] = dict(start=s["start"], end=s["end"], text=s["text"].strip(),
                                                       avg_logprob=s.get("avg_logprob"), why=label)
    return sorted(chosen.values(), key=lambda x: x["start"])


PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>진단 라벨링</title><style>
:root{--bg:#fafafa;--fg:#1d1d1f;--mut:#666;--card:#fff;--line:#ddd;--acc:#2563eb}
@media (prefers-color-scheme:dark){:root{--bg:#111;--fg:#eee;--mut:#aaa;--card:#1b1b1b;--line:#333;--acc:#60a5fa}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif;padding:16px;max-width:760px;margin:auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:12px 0}
.t{font-size:18px;margin:8px 0}.mut{color:var(--mut);font-size:13px}button{font:inherit;padding:8px 12px;margin:4px 4px 4px 0;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button.on{background:var(--acc);color:#fff;border-color:var(--acc)}input{font:inherit;width:100%;padding:6px;box-sizing:border-box;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px}
.bar{height:6px;background:var(--line);border-radius:3px}.bar i{display:block;height:6px;background:var(--acc);border-radius:3px}
</style></head><body>
<h2>10/7 수업 · 30줄 정답 표시</h2>
<p class="mut">▶ 로 그 구간만 듣고 ① <b>목소리로만</b> 누가 말했는지 ② 적힌 글이 <b>소리와 같은지</b>만 고르세요.
내가 틀리게 말했고 글도 그대로 적혔으면 <b>"같음"</b>입니다. 모르면 추측하지 말고 "모르겠음"/"잘 안 들림".
단축키: 스페이스=재생 · 1~4=화자 · Q/W/E=글 · ←/→=이전/다음</p>
<audio id="a" src="__AUDIO__" preload="auto"></audio>
<div class="bar"><i id="p"></i></div><div id="card" class="card"></div>
<button onclick="go(-1)">◀ 이전</button><button onclick="go(1)">다음 ▶</button><button onclick="save()">💾 결과 저장</button>
<script>
const L=__LINES__, KEY="diag-label-2026-10-07"; let i=0, ans={};
try{const s=JSON.parse(localStorage.getItem(KEY)||"{}"); ans=s.ans||{}; i=s.i||0}catch(e){}
const a=document.getElementById('a'); let stopAt=0;
a.addEventListener('timeupdate',()=>{if(stopAt&&a.currentTime>=stopAt){a.pause();stopAt=0}});
function play(){const l=L[i];a.currentTime=Math.max(0,l.start-0.3);stopAt=l.end+0.3;a.play()}
function pick(k,v){ans[i]=ans[i]||{};ans[i][k]=v;keep();show()}
function keep(){try{localStorage.setItem(KEY,JSON.stringify({ans,i}))}catch(e){}}
function b(k,v,t){const on=(ans[i]||{})[k]===v?' class="on"':'';return `<button${on} onclick="pick('${k}','${v}')">${t}</button>`}
function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function show(){const l=L[i],x=ans[i]||{};
 document.getElementById('p').style.width=(100*Object.keys(ans).filter(k=>ans[k].speaker&&ans[k].heard).length/L.length)+'%';
 document.getElementById('card').innerHTML=`<div class="mut">${i+1} / ${L.length} · ${l.start.toFixed(1)}~${l.end.toFixed(1)}초</div>
 <div class="t">"${esc(l.text)}"</div><button onclick="play()">▶ 듣기</button>
 <p>① 누가 말했나요?<br>${b('speaker','joey','Joey(나)')}${b('speaker','tutor','튜터')}${b('speaker','both','겹침')}${b('speaker','unknown','모르겠음')}</p>
 <p>② 글이 소리와 같나요?<br>${b('heard','same','같음')}${b('heard','diff','다름')}${b('heard','unclear','잘 안 들림')}</p>
 ${x.heard==='diff'?`<input placeholder="실제로 들린 말 (선택)" value="${esc(x.said||'')}" oninput="ans[i].said=this.value;keep()">`:''}`}
function go(d){i=Math.min(L.length-1,Math.max(0,i+d));keep();show()}
function save(){const out=L.map((l,k)=>Object.assign({idx:k,start:l.start,end:l.end,text:l.text},ans[k]||{}));
 const u=URL.createObjectURL(new Blob([JSON.stringify(out,null,1)],{type:'application/json'}));
 const e=document.createElement('a');e.href=u;e.download='labels-2026-10-07.json';e.click()}
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;const m={'1':['speaker','joey'],'2':['speaker','tutor'],'3':['speaker','both'],'4':['speaker','unknown'],'q':['heard','same'],'w':['heard','diff'],'e':['heard','unclear']};
 if(e.key===' '){e.preventDefault();play()}else if(e.key==='ArrowRight')go(1);else if(e.key==='ArrowLeft')go(-1);else if(m[e.key.toLowerCase()])pick(...m[e.key.toLowerCase()])});
show();
</script></body></html>"""


def make():
    arch = load_archive(os.path.join(INPUT, ARCHIVE_NAME))
    rec = arch.get(SAMPLES[DATE])
    if not rec:
        raise SystemExit("❌ 10/07 원본 없음 — prep 먼저")
    lines = read_json(PICKS) or select(rec.get("segments") or [])
    atomic_write_json(PICKS, lines)  # 한 번 고르면 고정
    out = _out_dir()
    os.makedirs(out, exist_ok=True)
    audio = SAMPLES[DATE]
    shutil.copy(os.path.join(INPUT, audio), os.path.join(out, audio))
    page = PAGE.replace("__AUDIO__", html.escape(audio)).replace(
        "__LINES__", json.dumps([{k: l[k] for k in ("start", "end", "text")} for l in lines], ensure_ascii=False))
    with open(os.path.join(out, "label.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"✅ {len(lines)}줄 · {out}/label.html (녹음 사본 포함)")


def speaker_of(text, transcript):
    """전사에서 그 문장과 가장 겹치는 줄의 화자 라벨."""
    best, who = 0.0, None
    for line in (transcript or "").splitlines():
        m = re.match(r"\s*\[(Tutor|Student)\]", line)
        if m:
            s = best_window(text, words(line))[0]
            if s > best:
                best, who = s, m.group(1)
    return who if best >= 0.5 else None


def auc(pos, neg):
    """pos(잘못 들림)의 신뢰도가 neg(같음)보다 낮을 확률."""
    if not pos or not neg:
        return None
    wins = sum((p < n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def score(path=None):
    path = path or max(glob.glob("/mnt/c/Users/*/Downloads/labels-2026-10-07*.json"), key=os.path.getmtime)
    labels = json.load(open(path, encoding="utf-8"))
    picks = read_json(PICKS)
    res = {}
    for vdir in sorted(glob.glob(os.path.join(OUT, "*"))):
        r = read_json(os.path.join(vdir, f"{DATE}.json"))
        if not r or "transcript" not in r:
            continue
        wrong = judged = 0
        for l in labels:
            truth = {"joey": "Student", "tutor": "Tutor"}.get(l.get("speaker"))
            if not truth:
                continue
            got = speaker_of(l["text"], r["transcript"])
            judged += 1
            wrong += got != truth
        res[os.path.basename(vdir)] = {"m2_wrong": wrong, "m2_judged": judged}
    diff = [p["avg_logprob"] for p, l in zip(picks, labels) if l.get("heard") == "diff" and p.get("avg_logprob") is not None]
    same = [p["avg_logprob"] for p, l in zip(picks, labels) if l.get("heard") == "same" and p.get("avg_logprob") is not None]
    a = auc(diff, same)
    res["M5"] = {"diff_lines": len(diff), "auc": a,
                 "verdict": "판정 불가(잘못 들림 5줄 미만)" if len(diff) < 5 else ("쓸모 있음" if a >= 0.70 else "쓸모 없음")}
    atomic_write_json(os.path.join(DIAG, "label_score.json"), res)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    {"make": make, "score": score}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print(__doc__))()

// 🌗 그림자판 비교 — 계산만 하는 함수 모음 (홈페이지 카드 · compare.html 이 같이 씀, node 로 검사 가능)
// Shadow-run comparison helpers shared by the homepage card and compare.html (pure, testable with node).
// 판정 기준(QUALITY_PLAN.md 10절): 판본을 가린 비교 10쌍 중 그림자판이 7회 이상 낫다고 뽑히면 G1 합격.
(function (root) {
  "use strict";
  var RAW = "https://raw.githubusercontent.com/ok0327-dot/english-feedback/shadow/";
  var GOAL = 10;   // 비교할 쌍 수 / pairs to compare
  var PASS = 7;    // 그림자판 승리 합격선 / shadow wins needed
  var DAYS = 14;   // 첫 그림자판부터 비교일까지 / days from first shadow version to comparison day
  var DAY_MS = 86400000;

  // runs.jsonl → 비교 대상(그림자판이 만들어진 수업) 목록과 첫 완료 시각
  function parseRuns(text) {
    var seen = {}, slugs = [], firstAt = null;
    String(text || "").split("\n").forEach(function (line) {
      line = line.trim();
      if (!line) return;
      var r;
      try { r = JSON.parse(line); } catch (e) { return; }   // 깨진 줄은 건너뜀
      if (!r || r.status !== "done" || typeof r.slug !== "string") return;
      if (!/^\d{4}-\d{2}-\d{2}(-\d+)?$/.test(r.slug)) return;
      if (!seen[r.slug]) { seen[r.slug] = true; slugs.push(r.slug); }
      if (typeof r.at === "string" && (!firstAt || r.at < firstAt)) firstAt = r.at;
    });
    slugs.sort();
    return { slugs: slugs, firstAt: firstAt };
  }

  // 'YYYY-MM-DD' 에 n일 더하기 (시간대와 무관한 달력 계산)
  function addDays(ymd, n) {
    var p = ymd.split("-").map(Number);
    return new Date(Date.UTC(p[0], p[1] - 1, p[2]) + n * DAY_MS).toISOString().slice(0, 10);
  }

  // 한국 시간 기준 오늘 'YYYY-MM-DD'
  function todayKST(nowMs) {
    return new Date((nowMs == null ? Date.now() : nowMs) + 9 * 3600000).toISOString().slice(0, 10);
  }

  function daysBetween(a, b) {   // b - a (일)
    var pa = a.split("-").map(Number), pb = b.split("-").map(Number);
    return Math.round((Date.UTC(pb[0], pb[1] - 1, pb[2]) - Date.UTC(pa[0], pa[1] - 1, pa[2])) / DAY_MS);
  }

  // 비교일 = 첫 그림자판 날짜(at 은 한국 시간 isoformat) + 14일
  function dueDate(firstAt) {
    return firstAt ? addDays(firstAt.slice(0, 10), DAYS) : null;
  }

  // 어느 글자(A/B)가 그림자판인지 — 수업마다 고정(같은 수업은 언제 열어도 같은 배정), 사용자에게는 숨김
  function shadowSide(slug) {
    var h = 2166136261;
    for (var i = 0; i < slug.length; i++) { h ^= slug.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; }
    return (h & 1) ? "A" : "B";
  }

  // 투표 집계 — votes = {slug: "A" | "B" | "same"}
  function tally(votes, slugs) {
    var t = { voted: 0, shadow: 0, main: 0, same: 0 };
    (slugs || Object.keys(votes || {})).forEach(function (s) {
      var v = votes && votes[s];
      if (v !== "A" && v !== "B" && v !== "same") return;
      t.voted++;
      if (v === "same") t.same++;
      else if (v === shadowSide(s)) t.shadow++;
      else t.main++;
    });
    t.complete = t.voted >= GOAL;
    t.pass = t.complete && t.shadow >= PASS;
    return t;
  }

  // 홈페이지 카드에 보일 상태
  function cardState(runsText, nowMs) {
    var r = parseRuns(runsText), k = r.slugs.length, due = dueDate(r.firstAt);
    if (!due) return { k: 0, due: null, left: null, ready: false,
                       text: "🌗 그림자판 비교 — 아직 그림자판이 없어요" };
    var left = daysBetween(todayKST(nowMs), due);
    var ready = left <= 0 || k >= GOAL;
    var when = left > 0 ? "D-" + left : (left === 0 ? "오늘" : "지났어요");
    var text = !ready ? "🌗 그림자판 비교 · " + due + " (" + when + ") · " + k + "/" + GOAL + "쌍 준비 →"
             : k >= GOAL ? "🌗 지금 그림자판 비교할 때예요! (" + GOAL + "/" + GOAL + "쌍 준비) →"
             : "🌗 비교일이 됐어요 — 아직 " + k + "/" + GOAL + "쌍 (10쌍이 모이면 정식 판정) →";
    return { k: k, due: due, left: left, ready: ready, text: text };
  }

  var api = { RAW: RAW, GOAL: GOAL, PASS: PASS, DAYS: DAYS, parseRuns: parseRuns, dueDate: dueDate,
              todayKST: todayKST, daysBetween: daysBetween, shadowSide: shadowSide, tally: tally,
              cardState: cardState };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ShadowCompare = api;
})(typeof self !== "undefined" ? self : this);

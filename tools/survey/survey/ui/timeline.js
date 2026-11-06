// The day at the receptor: a lane per source, a tick per pass, and the 1 s sound level. Zoom, pan and the time window.
"use strict";

// Time in the timeline is seconds from the day's start. state.view.timeline is the [from, to]
// shown, or null for the whole day.
const TL = { L: 92, R: 1188, laneTop: 8, laneH: 18, gap: 6, levelH: 110 };
const DAY_S = 86400, MIN_SPAN_S = 60;
const TIME_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600];
const timeView = () => state.view.timeline || [0, DAY_S];
let levelsBy = new Map();  // receptor -> [[t, dB], ...] in time order
function indexLevels() {
  levelsBy = new Map();
  for (const [t, r, db] of state.data.levels) {
    if (!levelsBy.has(r)) levelsBy.set(r, []);
    levelsBy.get(r).push([t, db]);
  }
  for (const lv of levelsBy.values()) lv.sort((a, b) => a[0] - b[0]);
}
function firstFrom(rows, t) {  // Index of the first row at or after t
  let lo = 0, hi = rows.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (rows[mid][0] < t) lo = mid + 1; else hi = mid; }
  return lo;
}
function nearestLevel(r, rel) {
  const lv = levelsBy.get(r) || [], i = firstFrom(lv, rel);
  const best = [lv[i - 1], lv[i]].filter(Boolean).sort((a, b) => Math.abs(a[0] - rel) - Math.abs(b[0] - rel))[0];
  return best && Math.abs(best[0] - rel) <= 30 ? best : null;
}
function timelineLayout() {
  const lanes = state.data.sources;  // In the server's order
  const levelTop = TL.laneTop + lanes.length * (TL.laneH + TL.gap) + 14;
  return { lanes, levelTop, levelBottom: levelTop + TL.levelH, height: levelTop + TL.levelH + 26 };
}
function drawTimeline(flights) {
  const svg = $("timeline"), d = state.data, lay = timelineLayout(), day0 = d.start;
  const [v0, v1] = timeView(), span = v1 - v0, W = TL.R - TL.L;
  svg.setAttribute("viewBox", `0 0 1200 ${lay.height}`);
  svg.replaceChildren();
  const sx = (t) => TL.L + ((t - day0 - v0) / span) * W;
  const inView = (t) => t >= day0 + v0 && t <= day0 + v1;
  const clip = el("clipPath", { id: "timeline-clip" }, el("defs", {}, svg));
  el("rect", { x: TL.L, y: 0, width: W, height: lay.height }, clip);
  const step = TIME_STEPS.find((s) => span / s <= 9) || TIME_STEPS[TIME_STEPS.length - 1];
  for (let s = Math.ceil(v0 / step) * step; s <= v1; s += step) {
    const x = sx(day0 + s);
    el("line", { x1: x, y1: TL.laneTop - 4, x2: x, y2: lay.levelBottom, class: "gridline" }, svg);
    const label = s >= DAY_S ? "24:00" : (step < 60 ? hms : hm)(day0 + s);
    text(svg, x, lay.levelBottom + 16, label, { "text-anchor": x > TL.R - 24 ? "end" : x < TL.L + 24 ? "start" : "middle" });
  }
  const r = $("f-receptor").value;
  const layer = el("g", { "clip-path": "url(#timeline-clip)" }, svg);
  lay.lanes.forEach((source, i) => {
    const y = TL.laneTop + i * (TL.laneH + TL.gap), c = colourOf(source);
    text(svg, TL.L - 8, y + 13, sourceName(source), { "text-anchor": "end", class: "ink" });
    for (const cov of d.coverage.filter((c2) => c2.source === source)) {
      const a = Math.max(day0 + v0, toT(cov.start_utc)), b = Math.min(day0 + v1, toT(cov.end_utc));
      if (a < b) el("rect", { x: sx(a), y, width: Math.max(1, sx(b) - sx(a)), height: TL.laneH, class: "lane", style: `--c: ${c}` }, layer);
    }
    for (const f of flights.filter((f2) => f2.source === source)) {
      const a = f.approaches[r];
      if (!a || !inView(toT(a.t))) continue;
      const x = sx(toT(a.t));
      el("line", { x1: x, y1: y + 2, x2: x, y2: y + TL.laneH - 2, class: "tick" + (f.pass_id === state.selected ? " selected" : ""), style: `--c: ${c}` }, layer);
      const hit = el("line", { x1: x, y1: y, x2: x, y2: y + TL.laneH, class: "tick-hit" }, layer);
      hit.addEventListener("mousemove", (e) => showTip(e, flightTip(f)));
      hit.addEventListener("mouseleave", hideTip);
      hit.addEventListener("click", () => select(f.pass_id, "timeline"));
    }
  });
  // Levels: the loudest second in each bucket a pixel or so wide, so peaks survive however far out
  const levels = levelsBy.get(r) || [];
  const lo = 30, hi = 90;
  const sy = (db) => lay.levelBottom - ((Math.min(hi, Math.max(lo, db)) - lo) / (hi - lo)) * TL.levelH;
  for (const db of [40, 60, 80]) {
    el("line", { x1: TL.L, y1: sy(db), x2: TL.R, y2: sy(db), class: "gridline" }, svg);
    text(svg, TL.L - 8, sy(db) + 4, `${db} dB`, { "text-anchor": "end" });
  }
  if (levels.length) {
    const bucket = span / W, gap = Math.max(5, 3 * bucket);  // A gap longer than this breaks the line
    const i0 = Math.max(0, firstFrom(levels, v0) - 1), i1 = Math.min(levels.length, firstFrom(levels, v1) + 1);
    let path = "", cur = null, best = 0, at = 0, last = null, gapNext = true;
    const flush = () => {
      if (cur === null) return;
      path += (gapNext ? "M" : "L") + `${sx(day0 + at).toFixed(1)},${sy(best).toFixed(1)}`;
      gapNext = false;
    };
    for (let i = i0; i < i1; i++) {
      const [t, db] = levels[i], b = Math.floor(t / bucket);
      if (b !== cur) {
        flush();
        if (last !== null && t - last > gap) gapNext = true;
        cur = b; best = db; at = t;
      } else if (db > best) { best = db; at = t; }
      last = t;
    }
    flush();
    if (path) el("path", { d: path, class: "level" }, layer);
  } else {
    text(svg, TL.L + 8, lay.levelTop + TL.levelH / 2, `No sound levels for ${receptor().label} on this day.`, {});
  }
  for (const e of d.events.filter((ev) => ev.receptor === r && inView(toT(ev.lmax_utc)))) {
    const x = sx(toT(e.lmax_utc)), y = sy(Number(e.lmax_db));
    const dot = el("circle", { cx: x, cy: y, r: 4, class: "lmax" + (e.event_class === "aircraft" ? "" : " other") }, layer);
    dot.addEventListener("mousemove", (ev) => showTip(ev, [h("div", {}, h("b", { text: `${fmt(Number(e.lmax_db), 1)} dB LAmax` })),
      h("div", { class: "row", text: `${hms(toT(e.lmax_utc))} · SEL ${fmt(Number(e.sel_db), 1)} dB · ${e.event_class === "aircraft" ? "aircraft event" : e.event_class === "other" ? "not an aircraft, by the source" : "unclassed event"}` })]));
    dot.addEventListener("mouseleave", hideTip);
  }
  if (state.window) {
    el("rect", { x: sx(state.window[0]), y: TL.laneTop - 4, width: Math.max(2, sx(state.window[1]) - sx(state.window[0])), height: lay.levelBottom - TL.laneTop + 4, class: "brush" }, layer);
  }
  timelineCross = el("line", { x1: 0, y1: TL.laneTop - 4, x2: 0, y2: lay.levelBottom, class: "crosshair", visibility: "hidden" }, svg);
  const shown = state.view.timeline ? `Showing ${(span < 3600 ? hms : hm)(day0 + v0)}–${v1 >= DAY_S ? "24:00" : (span < 3600 ? hms : hm)(day0 + v1)}` : "Whole day";
  $("window-note").textContent = `${shown}${state.window ? ` · window ${hm(state.window[0])}–${hm(state.window[1])}` : ""} · UTC`;
  $("window-reset").hidden = $("window-zoom").hidden = !state.window;
  $("timeline-reset").hidden = !state.view.timeline;
}
let timelineCross = null;
function setTimeView(v0, v1) {
  const span = Math.min(DAY_S, Math.max(MIN_SPAN_S, v1 - v0)), a = Math.min(DAY_S - span, Math.max(0, v0));
  state.view.timeline = span >= DAY_S ? null : [a, a + span];
  redraw("timeline");
}
function setupTimeline() {
  const svg = $("timeline"), W = TL.R - TL.L;
  const frac = (p) => (Math.min(TL.R, Math.max(TL.L, p.x)) - TL.L) / W;
  const tAt = (p) => { const [v0, v1] = timeView(); return state.data.start + v0 + frac(p) * (v1 - v0); };
  const unitsPerPixel = () => { const m = svg.getScreenCTM(); return m ? 1 / m.a : 1; };
  // Scroll to zoom about the pointer; scroll sideways, or with Shift, to pan
  svg.addEventListener("wheel", (event) => {
    if (!state.data) return;
    const p = svgPoint(svg, event);
    if (!p) return;
    event.preventDefault();
    hideTip();
    const unit = (n) => (event.deltaMode === 1 ? n * 16 : event.deltaMode === 2 ? n * 400 : n);
    let dx = unit(event.deltaX), dy = unit(event.deltaY);
    if (event.shiftKey && !dx) { dx = dy; dy = 0; }
    const [v0, v1] = timeView(), span = v1 - v0;
    if (Math.abs(dx) > Math.abs(dy)) {
      const ds = (dx * unitsPerPixel() / W) * span;
      setTimeView(v0 + ds, v1 + ds);
    } else {
      const k = Math.exp(Math.max(-1, Math.min(1, dy / 300))), c = v0 + frac(p) * span, f = frac(p);
      const next = Math.min(DAY_S, Math.max(MIN_SPAN_S, span * k));
      setTimeView(c - f * next, c - f * next + next);
    }
  }, { passive: false });
  // Drag to choose a window; Shift-drag to pan. Nothing is captured until the pointer has moved,
  // so a click still reaches a tick.
  let start = null;
  svg.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || !state.data) return;
    const p = svgPoint(svg, event);
    if (!p || p.x < TL.L) return;
    start = { t: tAt(p), x: event.clientX, id: event.pointerId, pan: event.shiftKey, view: timeView(), moved: false };
  });
  svg.addEventListener("pointermove", (event) => {
    const p = svgPoint(svg, event);
    if (!p || !state.data) return;
    if (timelineCross) {
      const show = p.x >= TL.L && p.x <= TL.R;
      timelineCross.setAttribute("visibility", show ? "visible" : "hidden");
      timelineCross.setAttribute("x1", p.x); timelineCross.setAttribute("x2", p.x);
      if (show && !(start && start.moved)) {
        const t = tAt(p), lv = nearestLevel($("f-receptor").value, t - state.data.start);
        showTip(event, [h("div", {}, h("b", { text: lv ? `${fmt(lv[1], 1)} dB` : "no level" })), h("div", { class: "row", text: `${hms(t)} UTC` })]);
      }
    }
    if (!start || event.pointerId !== start.id) return;
    if (!start.moved) {
      if (Math.abs(event.clientX - start.x) < 4) return;
      start.moved = true;
      svg.setPointerCapture(event.pointerId);
      if (start.pan) svg.classList.add("dragging");
      hideTip();
    }
    if (start.pan) {
      const [v0, v1] = start.view, ds = -((event.clientX - start.x) * unitsPerPixel() / W) * (v1 - v0);
      setTimeView(v0 + ds, v1 + ds);
    } else {
      const t = tAt(p);
      state.window = [Math.min(start.t, t), Math.max(start.t, t)];
      redraw("timeline");
    }
  });
  svg.addEventListener("pointerleave", () => { hideTip(); if (timelineCross) timelineCross.setAttribute("visibility", "hidden"); });
  const end = (event) => {
    if (!start || event.pointerId !== start.id) return;
    const { moved, pan } = start;
    start = null;
    svg.classList.remove("dragging");
    if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
    if (moved && !pan) { state.view.plan = state.view.profile = null; render(); }
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
  svg.addEventListener("dblclick", (event) => { event.preventDefault(); setTimeView(0, DAY_S); });
  $("timeline-reset").addEventListener("click", () => setTimeView(0, DAY_S));
  $("window-reset").addEventListener("click", () => { state.window = null; render(); });
  $("window-zoom").addEventListener("click", () => {
    const [a, b] = state.window, pad = (b - a) * 0.1, day0 = state.data.start;
    setTimeView(a - day0 - pad, b - day0 + pad);
  });
}
function shownFlightsIgnoringWindow() {
  const w = state.window;
  state.window = null;
  const all = shownFlights();
  state.window = w;
  return all;
}

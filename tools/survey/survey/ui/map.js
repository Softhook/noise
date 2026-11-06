// The plan view of tracks around the receptor, the height profile, and zooming and panning them.
"use strict";

// An SVG path through a track's points, broken wherever positions are missing for more than
// BREAK_S (a gap in the data, or points filtered out), so no line is drawn that wasn't flown.
const BREAK_S = 30;
// A null in pts also breaks the line: points were left out there.
function pathOf(pts, X, Y) {
  let d = "", prev = null;
  for (const p of pts) {
    if (p === null) { prev = null; continue; }
    d += (prev === null || p[0] - prev > BREAK_S ? "M" : "L") + `${X(p).toFixed(1)},${Y(p).toFixed(1)}`;
    prev = p[0];
  }
  return d;
}
// The points for which inside(p) holds, with their neighbours either side so lines run on to the
// edge of the view, and a null wherever points were left out. usable(p) says a neighbour can be drawn.
function nearby(all, inside, usable) {
  const ok = (p) => p !== null && p !== undefined && (!usable || usable(p));
  const keep = all.map((p) => ok(p) && inside(p));
  const out = [];
  let gap = false;
  all.forEach((p, i) => {
    if (ok(p) && (keep[i] || keep[i - 1] || keep[i + 1])) {
      if (gap && out.length) out.push(null);
      out.push(p);
      gap = false;
    } else gap = true;
  });
  return out;
}
const drawn = (pts) => pts.filter((p) => p !== null).length;
function drawOrder(flights) {
  const rank = (f) => (f.pass_id === state.selected ? 2 : 1);
  return flights.slice().sort((a, b) => rank(a) - rank(b));
}
function drawTrack(parent, d, f) {
  const selected = f.pass_id === state.selected;
  if (selected) el("path", { d, class: "ring" }, parent);
  el("path", { d, class: "track" + (isRadar(f.source) ? " radar" : ""), stroke: colourOf(f.source),
    "stroke-width": selected ? 3 : null, opacity: state.selected && !selected ? 0.25 : 0.9 }, parent);
  const hit = el("path", { d, class: "hit" }, parent);
  hit.addEventListener("mousemove", (e) => showTip(e, flightTip(f)));
  hit.addEventListener("mouseleave", hideTip);
  hit.addEventListener("click", () => { if (!dragged) select(f.pass_id, "map"); });
}
const PLAN = { C: 300, H: 270 };
const PROFILE_HALF_WIDTH_M = 3000;  // The profile shows tracks within this far north or south of the receptor
const PROFILE = { L: 56, Rt: 585, T: 20, B: 550 };
const planView = () => state.view.plan || { cx: 0, cy: 0, half: 6000 };
function ringsFor(half) {
  return [0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50].filter((km) => km * 1000 >= half / 10 && km * 1000 <= half * 1.45);
}
function windowed(pts) {
  if (!state.window) return pts;
  const [a, b] = state.window;
  return pts.filter((p) => p[0] >= a - 60 && p[0] <= b + 60);  // A little either side, so lines run on
}
function drawPlan(flights) {
  const svg = $("plan"), v = planView(), { C, H } = PLAN;
  svg.replaceChildren();
  const sx = (x) => C + ((x - v.cx) / v.half) * H, sy = (y) => C - ((y - v.cy) / v.half) * H;
  const clip = el("clipPath", { id: "plan-clip" }, el("defs", {}, svg));
  el("rect", { x: C - H, y: C - H, width: 2 * H, height: 2 * H }, clip);
  const grid = el("g", { "clip-path": "url(#plan-clip)" }, svg);
  for (const km of ringsFor(v.half)) {
    const rr = (km * 1000 / v.half) * H;
    el("circle", { cx: sx(0), cy: sy(0), r: rr, class: "gridline" }, grid);
    const ux = sx(0) > C ? -0.7071 : 0.7071, uy = sy(0) > C ? -0.7071 : 0.7071;
    const lx = sx(0) + rr * ux, ly = sy(0) + rr * uy;
    if (lx > C - H && lx < C + H && ly > C - H + 10 && ly < C + H) {
      text(grid, lx + (ux > 0 ? 4 : -4), ly + (uy > 0 ? 12 : -4), km < 1 ? `${km * 1000} m` : `${km} km`, { "text-anchor": ux > 0 ? "start" : "end" });
    }
  }
  el("line", { x1: C - H, y1: sy(0), x2: C + H, y2: sy(0), class: "gridline" }, grid);
  el("line", { x1: sx(0), y1: C - H, x2: sx(0), y2: C + H, class: "gridline" }, grid);
  text(svg, C, C - H - 10, "N", { "text-anchor": "middle", class: "ink" });
  const layer = el("g", { "clip-path": "url(#plan-clip)" }, svg);
  const reach = v.half * 1.5;
  let shown = 0;
  for (const f of drawOrder(flights)) {
    const pts = nearby(windowed(local[trackKey(f)] || []), (p) => Math.abs(p[1] - v.cx) <= reach && Math.abs(p[2] - v.cy) <= reach);
    if (drawn(pts) < 2) continue;
    shown++;
    drawTrack(layer, pathOf(pts, (p) => sx(p[1]), (p) => sy(p[2])), f);
  }
  const mark = el("g", { "clip-path": "url(#plan-clip)" }, svg);
  el("circle", { cx: sx(0), cy: sy(0), r: 6, class: "receptor" }, mark);
  text(mark, sx(0) + 10, sy(0) + 16, receptor().label, { class: "ink" });
  const across = 2 * v.half;
  text(svg, C - H, C + H + 22, `View ${across >= 2000 ? fmt(across / 1000, across >= 20000 ? 0 : 1) + " km" : Math.round(across) + " m"} across`);
  $("plan-count").textContent = `${shown} tracks drawn`;
  $("plan-reset").hidden = !state.view.plan;
}
function profileSets(flights) {
  const sets = [];
  for (const f of drawOrder(flights)) {
    const pts = nearby(windowed(local[trackKey(f)] || []), (p) => Math.abs(p[2]) <= PROFILE_HALF_WIDTH_M, (p) => p[3] !== null);
    if (drawn(pts) >= 2) sets.push([f, pts]);
  }
  return sets;
}
function profileView(sets) {
  if (state.view.profile) return state.view.profile;
  let top = 0;
  for (const [, pts] of sets) for (const p of pts) if (p && Math.abs(p[1]) <= 6000) top = Math.max(top, p[3]);
  return { x0: -6000, x1: 6000, h0: 0, h1: Math.min(4000, Math.max(300, top * 1.05)) };
}
function drawProfile(flights) {
  const svg = $("profile"), { L, Rt, T, B } = PROFILE;
  svg.replaceChildren();
  const sets = profileSets(flights), v = profileView(sets);
  const sx = (x) => L + ((x - v.x0) / (v.x1 - v.x0)) * (Rt - L), sy = (hh) => B - ((hh - v.h0) / (v.h1 - v.h0)) * (B - T);
  const clip = el("clipPath", { id: "profile-clip" }, el("defs", {}, svg));
  el("rect", { x: L, y: T, width: Rt - L, height: B - T }, clip);
  const yStep = niceStep(v.h1 - v.h0, 6);
  for (let y = Math.ceil(v.h0 / yStep) * yStep; y <= v.h1; y += yStep) {
    el("line", { x1: L, y1: sy(y), x2: Rt, y2: sy(y), class: Math.abs(y) < yStep / 2 ? "axisline" : "gridline" }, svg);
    text(svg, L - 8, sy(y) + 4, Math.round(y).toLocaleString("en-GB"), { "text-anchor": "end" });
  }
  text(svg, 12, T - 6, "m");
  const xStep = niceStep((v.x1 - v.x0) / 1000, 6) * 1000, digits = xStep < 1000 ? (xStep < 100 ? 2 : 1) : 0;
  for (let x = Math.ceil(v.x0 / xStep) * xStep; x <= v.x1; x += xStep) text(svg, sx(x), B + 18, fmt(x / 1000, digits), { "text-anchor": "middle" });
  text(svg, Rt, B + 36, `km east of ${receptor().label}`, { "text-anchor": "end" });
  const layer = el("g", { "clip-path": "url(#profile-clip)" }, svg);
  if (v.x0 <= 0 && v.x1 >= 0) el("line", { x1: sx(0), y1: T, x2: sx(0), y2: B, class: "axisline" }, layer);
  const span = v.x1 - v.x0;
  for (const [f, all] of sets) {
    const pts = nearby(all, (p) => p[1] >= v.x0 - span / 2 && p[1] <= v.x1 + span / 2);
    if (drawn(pts) < 2) continue;
    drawTrack(layer, pathOf(pts, (p) => sx(p[1]), (p) => sy(p[3])), f);
  }
  $("profile-reset").hidden = !state.view.profile;
}

// ---------- zoom and pan (as in the ADS-B viewer) ----------
const ZOOM = {
  plan: {
    zoom(p, k) {
      const v = planView(), { C, H } = PLAN;
      const half = Math.min(60000, Math.max(50, v.half * k));
      const x = v.cx + ((p.x - C) / H) * v.half, y = v.cy - ((p.y - C) / H) * v.half, f = half / v.half;
      state.view.plan = { cx: x - (x - v.cx) * f, cy: y - (y - v.cy) * f, half };
    },
    pan(s, dx, dy) { const m = s.half / PLAN.H; state.view.plan = { cx: s.cx - dx * m, cy: s.cy + dy * m, half: s.half }; },
    current: () => planView(),
  },
  profile: {
    zoom(p, k) {
      const v = profileView(profileSets(shownFlights())), { L, Rt, T, B } = PROFILE;
      const px = Math.min(Rt, Math.max(L, p.x)), py = Math.min(B, Math.max(T, p.y));
      const x = v.x0 + ((px - L) / (Rt - L)) * (v.x1 - v.x0), y = v.h0 + ((B - py) / (B - T)) * (v.h1 - v.h0);
      const kx = Math.min(100000, Math.max(50, (v.x1 - v.x0) * k)) / (v.x1 - v.x0);
      const ky = Math.min(20000, Math.max(5, (v.h1 - v.h0) * k)) / (v.h1 - v.h0);
      state.view.profile = { x0: x - (x - v.x0) * kx, x1: x + (v.x1 - x) * kx, h0: y - (y - v.h0) * ky, h1: y + (v.h1 - y) * ky };
    },
    pan(s, dx, dy) {
      const { L, Rt, T, B } = PROFILE, mx = (s.x1 - s.x0) / (Rt - L), my = (s.h1 - s.h0) / (B - T);
      state.view.profile = { x0: s.x0 - dx * mx, x1: s.x1 - dx * mx, h0: s.h0 + dy * my, h1: s.h1 + dy * my };
    },
    current: () => profileView(profileSets(shownFlights())),
  },
};
const pending = new Set();
function redraw(chart) {
  if (!pending.size) requestAnimationFrame(() => {
    const flights = shownFlights();
    if (pending.has("timeline")) drawTimeline(shownFlights(null));
    if (pending.has("plan")) drawPlan(flights);
    if (pending.has("profile")) drawProfile(flights);
    pending.clear();
  });
  pending.add(chart);
}
let dragged = false;
function makeZoomable(chart) {
  const svg = $(chart), z = ZOOM[chart];
  svg.addEventListener("wheel", (event) => {
    if (!state.data) return;
    const p = svgPoint(svg, event);
    if (!p) return;
    event.preventDefault();
    const lines = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaMode === 2 ? event.deltaY * 400 : event.deltaY;
    z.zoom(p, Math.exp(Math.max(-1, Math.min(1, lines / 300))));
    hideTip();
    redraw(chart);
  }, { passive: false });
  let start = null;
  svg.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || !state.data) return;
    const p = svgPoint(svg, event);
    if (!p) return;
    dragged = false;
    start = { p, client: [event.clientX, event.clientY], view: { ...z.current() }, id: event.pointerId };
  });
  svg.addEventListener("pointermove", (event) => {
    if (!start || event.pointerId !== start.id) return;
    if (!dragged) {
      if (Math.hypot(event.clientX - start.client[0], event.clientY - start.client[1]) < 4) return;
      dragged = true;
      svg.setPointerCapture(event.pointerId);
      svg.classList.add("dragging");
      hideTip();
    }
    const p = svgPoint(svg, event);
    if (p) { z.pan(start.view, p.x - start.p.x, p.y - start.p.y); redraw(chart); }
  });
  const end = (event) => {
    if (!start || event.pointerId !== start.id) return;
    start = null;
    svg.classList.remove("dragging");
    if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
  const reset = () => { state.view[chart] = null; redraw(chart); };
  svg.addEventListener("dblclick", (event) => { event.preventDefault(); reset(); });
  $(`${chart}-reset`).addEventListener("click", reset);
}

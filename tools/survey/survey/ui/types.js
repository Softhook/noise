// The "By aircraft type" panel: one row per type, a lane in each row per source, a dot per flight
// and a tick at each lane's median. As in the ADS-B viewer, but for every source, so the sources can
// be compared type by type.
"use strict";

// What the panel can show. of: "flight" (a value per source's flight, from its closest approach to
// the receptor) or "pass" (one value per pass). edge: the value is doubtful when the closest
// approach is at an edge of the source's data (approaches' at_track_end).
const MEASURES = {
  // Signed, unlike the ADS-B viewer's, which shows arrivals only: a climb and a descent at the same
  // angle would otherwise sit together
  path_angle_deg: { label: "Path angle (°, descending negative)", of: "flight", digits: 2, edge: false,
    value: (f, a) => (a && a.path_angle_deg !== null && a.path_angle_deg !== undefined ? a.path_angle_deg : null),
    refs: [[-5.5, "5.5° ILS"], [-4.49, "4.49° RNP-AR"]] },
  ground_m: { label: "Ground distance at closest approach (m)", of: "flight", digits: 0, edge: true, value: (f, a) => (a ? a.ground_m : null) },
  height_m: { label: "Height at closest approach (m above sea level)", of: "flight", digits: 0, edge: true, value: (f, a) => (a ? a.height_m : null) },
  slant_m: { label: "Closest distance to the microphone (m)", of: "flight", digits: 0, edge: true, value: (f, a) => (a ? a.slant_m : null) },
  lmax_db: { label: "LAmax (dB)", of: "pass", digits: 1, edge: false,
    value: (p) => { const e = eventNear(p.id); return e ? Number(e.lmax_db) : null; } },
};
const median = (values) => {
  const v = values.slice().sort((a, b) => a - b), n = v.length;
  return !n ? null : n % 2 ? v[(n - 1) / 2] : (v[n / 2 - 1] + v[n / 2]) / 2;
};
// A pass's type: the resolved one (from the fleet table's register entry first), or else the
// first one given, in source order, by any of its flights that day, whatever is shown. So a pass
// sits in the same row whichever sources are switched on.
function passTypes() {
  const flightsOf = new Map();
  for (const f of state.data.flights) {
    if (!flightsOf.has(f.pass_id)) flightsOf.set(f.pass_id, []);
    flightsOf.get(f.pass_id).push(f);
  }
  const by = new Map();
  for (const [passId, fs] of flightsOf) {
    const type = passType(passId, fs);
    if (type) by.set(passId, type);
  }
  return by;
}
// The panel's rows: [{type, passes, lanes: [{source, dots: [{f, pass, v, edge}], median}]}], types
// in name order, "unknown" last; lanes in source order. A dot whose value is at an edge of its
// source's data is kept, but left out of the median. For a "pass" measure, the one lane's source is null.
function typeRows(flights, measureKey, r) {
  const m = MEASURES[measureKey], types = passTypes(), rows = new Map();
  const row = (passId) => {
    const type = types.get(passId) || "unknown";
    if (!rows.has(type)) rows.set(type, { type, passIds: new Set(), lanes: new Map() });
    return rows.get(type);
  };
  const add = (rw, source, dot) => {
    if (!rw.lanes.has(source)) rw.lanes.set(source, []);
    rw.lanes.get(source).push(dot);
    rw.passIds.add(dot.pass);
  };
  if (m.of === "pass") {
    for (const p of passesOf(flights)) {
      const v = m.value(p);
      if (typeof v === "number" && Number.isFinite(v)) add(row(p.id), null, { f: null, p, pass: p.id, v, edge: false });
    }
  } else {
    for (const f of flights) {
      const a = f.approaches[r], v = m.value(f, a);
      if (typeof v !== "number" || !Number.isFinite(v)) continue;
      add(row(f.pass_id), f.source, { f, pass: f.pass_id, v, edge: !!(m.edge && a && a.at_track_end) });
    }
  }
  return [...rows.values()]
    .sort((a, b) => (a.type === "unknown") - (b.type === "unknown") || (a.type < b.type ? -1 : a.type > b.type ? 1 : 0))
    .map((rw) => ({
      type: rw.type, passes: rw.passIds.size,
      lanes: [...rw.lanes.entries()].sort((a, b) => (a[0] === null ? 0 : bySource(a[0], b[0])))
        .map(([source, dots]) => ({ source, dots, median: median(dots.filter((d) => !d.edge).map((d) => d.v)) })),
    }));
}

// A small fixed offset within the lane for each pass, so dots with the same value don't hide each
// other, and a pass's dot stays put from one draw to the next.
function jitter(id) {
  let hash = 0;
  for (const c of id) hash = (hash * 31 + c.charCodeAt(0)) | 0;
  return ((hash >>> 0) % 1000) / 1000 - 0.5;
}
function drawTypes(flights) {
  const svg = $("types");
  svg.replaceChildren();
  const r = $("f-receptor").value, key = $("f-measure").value, m = MEASURES[key];
  const rows = typeRows(flights, key, r);
  const W = 1200, L = 120, Rt = 1180, T = 22, LANE = 14, PAD = 6;
  const heights = rows.map((rw) => Math.max(28, rw.lanes.length * LANE + 2 * PAD));
  const bottom = T + heights.reduce((s, x) => s + x, 0);
  svg.setAttribute("viewBox", `0 0 ${W} ${bottom + 34}`);
  const passes = new Set(rows.flatMap((rw) => rw.lanes.flatMap((ln) => ln.dots.map((d) => d.pass))));
  $("types-count").textContent = rows.length ? `${passes.size} passes, ${rows.length} types` : "";
  if (!rows.length) {
    svg.setAttribute("viewBox", `0 0 ${W} 60`);
    text(svg, L, 34, m.of === "pass" ? "No pass shown has a noise event at this receptor." : "No flight shown has this measure at this receptor.");
    return;
  }
  let lo = Infinity, hi = -Infinity;
  for (const rw of rows) for (const ln of rw.lanes) for (const d of ln.dots) { lo = Math.min(lo, d.v); hi = Math.max(hi, d.v); }
  // The approach angles, only when something shown is descending, so a day of departures isn't squeezed
  const refs = lo < 0 ? m.refs || [] : [];
  for (const [v] of refs) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  const pad = (hi - lo) * 0.06 || Math.max(1, Math.abs(lo) * 0.05);
  lo -= pad; hi += pad;
  const sx = (v) => L + ((v - lo) / (hi - lo)) * (Rt - L);
  const step = niceStep(hi - lo, 8), digits = step < 1 ? (step < 0.1 ? 2 : 1) : 0;
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
    el("line", { x1: sx(v), y1: T, x2: sx(v), y2: bottom, class: "gridline" }, svg);
    text(svg, sx(v), bottom + 16, fmt(Math.abs(v) < step / 1e6 ? 0 : v, digits), { "text-anchor": "middle" });
  }
  text(svg, Rt, bottom + 32, m.label, { "text-anchor": "end" });
  for (const [v, name] of refs) {
    el("line", { x1: sx(v), y1: T - 6, x2: sx(v), y2: bottom, class: "ref" }, svg);
    text(svg, sx(v) + 4, T - 8, name, { class: "ink" });
  }
  const selectedDots = [];
  let y = T;
  rows.forEach((rw, i) => {
    const hRow = heights[i], top = y + (hRow - rw.lanes.length * LANE) / 2;
    text(svg, L - 10, y + hRow / 2 + 4, `${rw.type} (${rw.passes})`, { "text-anchor": "end", class: "ink" });
    el("line", { x1: L, y1: y + hRow, x2: Rt, y2: y + hRow, class: "gridline" }, svg);
    rw.lanes.forEach((ln, j) => {
      const cy = top + j * LANE + LANE / 2;
      const colour = ln.source === null ? "var(--text-2)" : colourOf(ln.source);
      for (const d of ln.dots) {
        const selected = d.pass === state.selected;
        if (selected) { selectedDots.push([d, cy, colour]); continue; }
        dot(svg, d, sx(d.v), cy + jitter(d.pass) * (LANE - 5), colour, false);
      }
      if (ln.median !== null) el("line", { x1: sx(ln.median), y1: cy - LANE / 2 + 1, x2: sx(ln.median), y2: cy + LANE / 2 - 1, class: "median" }, svg);
    });
    y += hRow;
  });
  // The selected pass's dots last, so they're on top
  for (const [d, cy, colour] of selectedDots) dot(svg, d, sx(d.v), cy + jitter(d.pass) * (LANE - 5), colour, true);

  function dot(parent, d, cx, cy, colour, selected) {
    const node = el("circle", {
      cx, cy, r: selected ? 6 : 4, class: "dot" + (d.edge ? " edge" : "") + (selected ? " selected" : ""),
      fill: d.edge ? null : colour, style: `--c: ${colour}`,
      opacity: state.selected && !selected ? 0.35 : 0.9,
    }, parent);
    node.addEventListener("mousemove", (e) => showTip(e, dotTip(d)));
    node.addEventListener("mouseleave", hideTip);
    node.addEventListener("click", () => select(d.pass, "types"));
  }
  function dotTip(d) {
    const line = h("div", { class: "row" }, h("b", { text: `${fmt(d.v, m.digits)}` }), ` · ${m.label}${d.edge ? " (at an edge of its data)" : ""}`);
    if (d.f) return [...flightTip(d.f), line];
    const reg = d.p.flights.map((f) => f.registration || f.callsign).find(Boolean) || d.pass;
    return [h("div", {}, h("b", { text: reg }), ` · ${d.p.flights.map((f) => f.type).find(Boolean) || "unknown type"}`),
      h("div", { class: "row", text: `Pass ${d.pass} · closest ${hms(d.p.t)}` }), line];
  }
}
function setupTypes() {
  $("f-measure").replaceChildren(...Object.entries(MEASURES).map(([k, m]) => h("option", { value: k, text: m.label })));
  $("f-measure").addEventListener("input", () => { if (state.data) drawTypes(shownFlights()); });
}

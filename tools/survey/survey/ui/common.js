// Shared by the other scripts: constants, page state, DOM and number helpers, the tooltip, the API, and which flights and passes are shown. Loaded first.
"use strict";

const SVG = "http://www.w3.org/2000/svg";
const $ = (id) => document.getElementById(id);
const COLOUR_SLOTS = ["adsb", "webtrak", "opensky", "adsblol"];  // Fixed colour slots (style.css); anything else is "other"
const SOURCE_NAMES = { adsb: "Garden ADS-B", webtrak: "WebTrak radar", opensky: "OpenSky", adsblol: "adsb.lol" };
const colourOf = (source) => `var(--src-${COLOUR_SLOTS.includes(source) ? source : "other"})`;
const sourceName = (s) => SOURCE_NAMES[s] || s;
// The order sources are listed in, everywhere on the page: the server's (state.data.sources, in
// survey/link.py's rank), ADS-B first and WebTrak last. So Δ height is always an ADS-B source
// minus the next source. A source the server didn't list goes last.
function bySource(a, b) {
  const order = (state.data && state.data.sources) || [];
  const ra = order.indexOf(a), rb = order.indexOf(b);
  return (ra < 0) - (rb < 0) || ra - rb || (a < b ? -1 : a > b ? 1 : 0);
}
// Radar tracks are drawn dashed: the sources whose positions are radar heights (positions.height_kind)
const isRadar = (source) => !!(state.radar && state.radar.has(source));
// Why a source has no flight in a pass (survey/explain.py), as the table puts it
const WHY = { "no data": "no data then", "outside its area": "outside its area", "above its ceiling": "above its ceiling", "unexplained": "missed" };
const unseenOf = (passId) => (state.data.unseen || {})[passId] || {};
// A pass's resolved identity (resolve.py): {registration, type, model, type_source, disagree}, or
// {} for a build made before it existed
const identityOf = (passId) => (state.data.identity || {})[passId] || {};
// Where a resolved type came from, in words
const REGISTER_NAMES = { uk: "the UK register", ch: "the Swiss register", ie: "the Irish register", lu: "the Luxembourg register" };
const typeNote = (id) => {
  const s = id.type_source || "";
  if (!s) return "";
  if (s === "manual") return "checked by hand";
  if (s.startsWith("register:")) return `from ${REGISTER_NAMES[s.slice(9)] || s.slice(9) + " register"}`;
  return `from ${sourceName(s)} only; not in the fleet table`;
};
// A pass's type: the resolved one, or else the first its flights give in source order
const passType = (passId, flights) => identityOf(passId).type
  || flights.slice().sort((a, b) => bySource(a.source, b.source)).map((f) => f.type).find(Boolean) || "";
const unexplained = (passId) => Object.entries(unseenOf(passId)).some(([s, why]) => why === "unexplained" && state.sources.has(s));

const state = {
  deployments: [], data: null, window: null, selected: null,
  sources: new Set(), off: new Set(), view: { plan: null, profile: null, timeline: null },
  radar: new Set(), eventOf: new Map(),
};

// ---------- helpers ----------
function el(name, attrs, parent) {
  const node = document.createElementNS(SVG, name);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}
function text(parent, x, y, content, attrs) {
  const node = el("text", Object.assign({ x, y }, attrs || {}), parent);
  node.textContent = content;
  return node;
}
function h(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "text") node.textContent = v;
    else if (k === "class") node.className = v;
    else if (k === "style") node.setAttribute("style", v);
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c !== null && c !== undefined) node.append(c);
  return node;
}
function fmt(v, digits) {
  if (v === null || v === undefined || v === "" || Number.isNaN(v)) return "–";
  return Number(v).toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
// A signed path angle (positive climbing), as the page puts it
const pathAngle = (deg) => `${fmt(Math.abs(deg), 2)}° ${deg > 0.5 ? "climbing" : deg < -0.5 ? "descending" : "level"}`;
const toT = (iso) => Date.parse(iso) / 1000;
const hms = (t) => new Date(t * 1000).toISOString().slice(11, 19);
const hm = (t) => new Date(t * 1000).toISOString().slice(11, 16);
function niceStep(span, target) {
  const raw = span / target, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / mag;
  return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag;
}
function svgPoint(svg, event) {
  const m = svg.getScreenCTM();
  return m ? new DOMPoint(event.clientX, event.clientY).matrixTransform(m.inverse()) : null;
}
function key(source, color, dashed) {
  return h("span", { class: "key" + (dashed ? " dashed" : ""), style: `--c: ${color}`, "aria-hidden": "true" });
}

// ---------- tooltip ----------
function showTip(event, rows) {
  const tip = $("tooltip");
  tip.replaceChildren(...rows);
  tip.style.display = "block";
  tip.style.left = Math.min(event.clientX + 14, window.innerWidth - tip.offsetWidth - 8) + "px";
  tip.style.top = Math.min(event.clientY + 14, window.innerHeight - tip.offsetHeight - 8) + "px";
}
function hideTip() { $("tooltip").style.display = "none"; }
function flightTip(f) {
  const r = $("f-receptor").value, a = f.approaches[r];
  const rows = [h("div", {}, key(f.source, colourOf(f.source), isRadar(f.source)), " ",
    h("b", { text: f.registration || f.callsign || f.source_id }), ` · ${f.type || "unknown type"}`)];
  rows.push(h("div", { class: "row", text: `${sourceName(f.source)}${f.callsign ? " · " + f.callsign : ""}${f.direction ? " · " + ({ A: "arrival", D: "departure", O: "other" }[f.direction] || f.direction) : ""}` }));
  if (a) rows.push(h("div", { class: "row", text: `Closest ${hms(toT(a.t))} · ${fmt(a.ground_m, 0)} m away · ${fmt(a.height_m, 0)} m up${a.at_track_end ? " (edge of its data)" : ""}` }));
  if (a && a.path_angle_deg !== null && a.path_angle_deg !== undefined) rows.push(h("div", { class: "row", text: `Path angle ${pathAngle(a.path_angle_deg)}` }));
  for (const [s, why] of Object.entries(unseenOf(f.pass_id))) {
    if (state.sources.has(s)) rows.push(h("div", { class: "row" + (why === "unexplained" ? " unexplained" : ""), text: `Not in ${sourceName(s)}: ${why === "unexplained" ? "should have seen it" : why}` }));
  }
  return rows;
}

// ---------- data ----------
async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || response.statusText);
  return body;
}

// Local metres east and north of the selected receptor, worked out once per receptor change.
let frame = null;
function makeFrame(r) {
  const lat0 = r.lat * Math.PI / 180;
  const a = 6378137, e2 = 0.00669437999014, s = Math.sin(lat0), w = Math.sqrt(1 - e2 * s * s);
  const kn = (a * (1 - e2) / w ** 3) * Math.PI / 180, ke = (a / w) * Math.cos(lat0) * Math.PI / 180;
  return (lat, lon) => [(lon - r.lon) * ke, (lat - r.lat) * kn];
}
let local = {};  // track key -> [[t, x, y, h], ...] for the current receptor
function projectTracks() {
  const r = receptor();
  frame = makeFrame(r);
  local = {};
  for (const [k, pts] of Object.entries(state.data.tracks)) local[k] = pts.map((p) => [p[0], ...frame(p[1], p[2]), p[3]]);
}
const receptor = () => state.data.receptors.find((r) => r.id === $("f-receptor").value) || state.data.receptors[0];
const trackKey = (f) => `${f.source}|${f.source_id}`;

// The flights shown: chosen sources, search, "several sources", and the time window (or another
// window, or null for none: the timeline shows the whole day's ticks whatever the window).
function shownFlights(timeWindow = state.window) {
  const d = state.data, search = $("f-search").value.trim().toLowerCase(), r = $("f-receptor").value;
  const within = Number($("f-within").value) || Infinity, below = Number($("f-below").value) || Infinity;
  const near = within < Infinity || below < Infinity;
  // A pass is kept whole when any source saw it come close enough, and low enough, at its closest approach
  const passSources = new Map(), passNear = new Set();
  for (const f of d.flights) {
    if (!passSources.has(f.pass_id)) passSources.set(f.pass_id, new Set());
    passSources.get(f.pass_id).add(f.source);
    const a = f.approaches[r];
    if (a && a.ground_m !== null && a.ground_m <= within && (a.height_m === null || a.height_m <= below)) passNear.add(f.pass_id);
  }
  return d.flights.filter((f) => {
    if (!state.sources.has(f.source)) return false;
    if (near && !passNear.has(f.pass_id)) return false;
    if ($("f-linked").checked && passSources.get(f.pass_id).size < 2) return false;
    if ($("f-unexplained").checked && !unexplained(f.pass_id)) return false;
    if (search && ![f.registration, f.callsign, f.type, f.pass_id].some((v) => (v || "").toLowerCase().includes(search))) return false;
    if (timeWindow) {
      const pts = local[trackKey(f)];
      if (!pts || pts[pts.length - 1][0] < timeWindow[0] || pts[0][0] > timeWindow[1]) return false;
    }
    return true;
  });
}
function passesOf(flights) {
  const map = new Map();
  for (const f of flights) {
    if (!map.has(f.pass_id)) map.set(f.pass_id, []);
    map.get(f.pass_id).push(f);
  }
  const r = $("f-receptor").value;
  const when = (fs) => Math.min(...fs.map((f) => (f.approaches[r] ? toT(f.approaches[r].t) : toT(f.first_utc))));
  return [...map.entries()].map(([id, fs]) => ({ id, flights: fs.sort((a, b) => bySource(a.source, b.source)), t: when(fs) }))
    .sort((a, b) => a.t - b.t);
}

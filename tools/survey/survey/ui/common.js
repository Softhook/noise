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
const unseenOf = (passId) => state.data.unseen[passId] || {};
// A pass's resolved identity (resolve.py): {registration, type, model, type_source, fleet, disagree}.
// Its type is the one the page shows everywhere: the register's, or else its highest-ranked source's.
const identityOf = (passId) => state.data.identity[passId] || {};
// Where a resolved type came from, in words. id.fleet (resolve.py) says why the fleet table didn't
// settle it
const REGISTER_NAMES = { uk: "the UK register", ch: "the Swiss register", ie: "the Irish register", lu: "the Luxembourg register" };
const FLEET_WHY = {
  "no registration": "no registration to look up",
  "not in the table": "not in the fleet table",
  "not found": "its register doesn't have it",
  "no type": "its register entry gives no type",
};
const typeNote = (id) => {
  const s = id.type_source || "";
  if (!s) return "";
  if (s === "manual") return "checked by hand";
  if (s.startsWith("register:")) return `from ${REGISTER_NAMES[s.slice(9)] || s.slice(9) + " register"}`;
  return `from ${sourceName(s)} only` + (FLEET_WHY[id.fleet] ? `; ${FLEET_WHY[id.fleet]}` : "");
};
// ICAO type designators (Doc 8643) -> the name people know the type by, for the types the survey
// sees. A designator not here is shown as it is.
const TYPE_NAMES = {
  A109: "Leonardo AW109", A19N: "Airbus A319neo", A20N: "Airbus A320neo", A21N: "Airbus A321neo",
  A319: "Airbus A319", A320: "Airbus A320", A321: "Airbus A321", A332: "Airbus A330-200", A333: "Airbus A330-300",
  A359: "Airbus A350-900", A35K: "Airbus A350-1000", A388: "Airbus A380", AT75: "ATR 72-500", AT76: "ATR 72-600",
  B38M: "Boeing 737 MAX 8", B738: "Boeing 737-800", B748: "Boeing 747-8", B763: "Boeing 767-300", B764: "Boeing 767-400",
  B772: "Boeing 777-200", B77L: "Boeing 777-200LR/F", B77W: "Boeing 777-300ER", B788: "Boeing 787-8",
  B789: "Boeing 787-9", B78X: "Boeing 787-10", BCS1: "Airbus A220-100", BCS3: "Airbus A220-300",
  BE20: "Beech King Air 200", C152: "Cessna 152", C17: "Boeing C-17", C172: "Cessna 172", C72R: "Cessna 172RG",
  C25A: "Cessna Citation CJ2", C25B: "Cessna Citation CJ3", C525: "Cessna Citation CJ1/M2",
  C56X: "Cessna Citation Excel/XLS", C680: "Cessna Citation Sovereign", C68A: "Cessna Citation Latitude",
  DA42: "Diamond DA42", DH8A: "Dash 8-100", DH8B: "Dash 8-200", DH8C: "Dash 8-300", DH8D: "Dash 8-400",
  E190: "Embraer 190", E195: "Embraer 195", E290: "Embraer E190-E2", E295: "Embraer E195-E2",
  E35L: "Embraer Legacy 600/650", E550: "Embraer Legacy 500/Praetor 600", E55P: "Embraer Phenom 300",
  E75L: "Embraer 175", EC35: "Airbus H135", EC45: "Airbus H145", EFOX: "Aeropro Eurofox", EUPA: "Europa",
  FA7X: "Dassault Falcon 7X", FA8X: "Dassault Falcon 8X", GL7T: "Bombardier Global 7500",
  GLEX: "Bombardier Global Express", GLF6: "Gulfstream G650", H25B: "Hawker 800", K35R: "Boeing KC-135R",
  LJ45: "Learjet 45", P180: "Piaggio P.180 Avanti", P28A: "Piper PA-28 Cherokee", P28R: "Piper PA-28R Arrow",
  P46T: "Piper Malibu Meridian", PRM1: "Beechcraft Premier I", TOBA: "Socata TB-10 Tobago",
};
const typeName = (code) => TYPE_NAMES[code] || "";
// A type as text: "E290 (Embraer E190-E2)", or the designator alone if it has no name here
const typeText = (code) => (code ? (typeName(code) ? `${code} (${typeName(code)})` : code) : "");
const passType = (passId) => identityOf(passId).type || "";
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
// A flight's type as its pass resolved it, with the source's own when that differs, so a tooltip
// never contradicts the table or the type panel's row
function flightTypeText(f) {
  const resolved = (f.pass_id && identityOf(f.pass_id).type) || f.type;
  if (!resolved) return "unknown type";
  return typeText(resolved) + (f.type && f.type !== resolved ? `; ${sourceName(f.source)} says ${f.type}` : "");
}
function flightTip(f) {
  const r = $("f-receptor").value, a = f.approaches[r];
  const rows = [h("div", {}, key(f.source, colourOf(f.source), isRadar(f.source)), " ",
    h("b", { text: f.registration || f.callsign || f.source_id }), ` · ${flightTypeText(f)}`)];
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
    if (search && ![f.registration, f.callsign, f.type, typeName(f.type), f.pass_id].some((v) => (v || "").toLowerCase().includes(search))) return false;
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

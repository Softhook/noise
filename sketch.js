/**
 * LCY Runway 27 Approach Slope & Acoustic Differential Model
 * Compares Current 5.5° Steep Approach vs Proposed 4.49° Shallow Approach (0 to 6.5 nm)
 * The controls are in index.html; this file holds the data, the model and the charts.
 */
// LCY Stage 3 Consultation Document: RWY 27 descends from 3,000 ft (Fig. 9), RWY 09 from 2,000 ft (Fig. 8).
// Two labels are replaced by the 4.49° slope value: 574 ft at 1 nm in Fig. 9 (547 ft) and 1,692 ft in Fig. 8 (1,656 ft).
const WAYPOINTS_BY_RUNWAY = {
  "27": [
    { nm: 0.0,  curr: 55,   prop: 70,   label: "Rwy 27", loc: "Woolwich" },
    { nm: 1.0,  curr: 640,  prop: 547,  label: "1nm",    loc: "Thamesmead" },
    { nm: 2.0,  curr: 1225, prop: 1024, label: "2nm",    loc: "Abbey Wood" },
    { nm: 3.0,  curr: 1810, prop: 1501, label: "3nm",    loc: "Belvedere" },
    { nm: 4.0,  curr: 2395, prop: 1978, label: "4nm",    loc: "Erith" },
    { nm: 5.03, curr: 3000, prop: 2472, label: "Curr TOD", loc: "Rainham" },
    { nm: 6.14, curr: 3000, prop: 3000, label: "Prop TOD", loc: "Purfleet" }
  ],
  "09": [
    { nm: 0.0,  curr: 55,   prop: 70,   label: "Rwy 09", loc: "Silvertown" },
    { nm: 1.0,  curr: 640,  prop: 547,  label: "1nm",    loc: "Royal Victoria" },
    { nm: 2.0,  curr: 1225, prop: 1024, label: "2nm",    loc: "Blackwall" },
    { nm: 3.0,  curr: 1810, prop: 1501, label: "3nm",    loc: "Limehouse" },
    { nm: 3.32, curr: 2000, prop: 1656, label: "Curr TOD", loc: "Rotherhithe Tunnel", locRow: 1 },
    { nm: 4.05, curr: 2000, prop: 2000, label: "Prop TOD", loc: "Wapping" }
  ]
};

const SOURCE_SLIDER = { min: -4.0, max: 3.0 };
const THRUST_SLIDER = { min: 0.0, max: 4.0 };
// Evidence ranges shown under the sliders; sources are listed in Documents/README.md
const SOURCE_RANGE_E190 = [-2.0, 1.1]; // Measured at Reagan National (about -2) to least favourable certificate pairing
const SOURCE_RANGE_E2 = [0.6, 1.5];    // Certificates: A320neo 92.0–92.9 vs E190-E2 91.4 EPNdB
const THRUST_RANGE = [0.0, 2.5];       // About 0 (LCY scheme, Heathrow trials) to about 2.5 (NASA turbojet study)

// LCY Stage 3 Consultation Document (Issue 1.1, Apr 2026), arrivals: Fig. 17 (RWY 27) and Fig. 18 (RWY 09).
// [km from threshold, E190 at 5.5° minus A320neo at 4.49°, dB(A) SEL]. Positive means the E190 is louder.
// These are net figures: the lower A320neo altitude is already included. The tables stop at 5 km.
const LCY_E190_ARRIVALS = {
  "27": [
    [0.5, 2.2], [1.0, 1.7], [1.5, 1.5], [2.0, 1.3], [2.5, 1.2],
    [3.0, 1.2], [3.5, 0.7], [4.0, 0.3], [4.5, -0.2], [5.0, -1.0]
  ],
  "09": [
    [0.5, 2.2], [1.0, 1.7], [1.5, 1.5], [2.0, 1.3], [2.5, 1.3],
    [3.0, 1.2], [3.5, 0.7], [4.0, 0.3], [4.5, -0.2], [5.0, -0.9]
  ]
};
const KM_PER_NM = 1.852;

const PRESETS = [
  {
    name: "Geometry",
    desc: "Isolates the 20log10(d1/d2) proximity & atmospheric effect of dropping from 5.5° to 4.49°.",
    sourceDelta: 0.0,
    thrustDelta: 0.0,
    sources: () => [
      `Same aircraft, thrust, speed and flaps on both slopes. Altitudes: LCY Consultation ${altitudeFigure()} (${activeRunway === "27" ? "its 1 nm label of 574 ft corrected to 547 ft" : "its 1,692 ft label replaced by slope value 1,656 ft"}).`,
      "Distance: 6 dB per doubling (Annex C p.41); SEL 10 log, standard rule. Air: 0.6 dB/1,000 ft, no source. Listener directly below path, flat ground."
    ]
  },
  {
    name: "Airport claim",
    desc: "LCY consultation Figs. 17–18: A320neo at 4.49° vs E190 at 5.5° (SEL, net). Dashed: no airport figures, estimate only.",
    sourceDelta: 0.0, // Not used: the airport publishes one net figure, which already includes source and thrust
    thrustDelta: 0.0,
    usesAirportTable: true,
    sources: () => [
      "AEDT 3g model, not measured. E190: 737-500 data +1.5 dB (LCY Annex C p.10). A320neo: unadjusted AEDT data on LCY profile at 4.49° (pp.8, 12).",
      "Thrust: estimated within flight profiles, no value published (p.7). Flap, gear, engine variant, weight, weather: none stated. Data: Consultation pp.30–31."
    ]
  },
  {
    name: "EASA empirical",
    desc: "EASA TCDSN approach delta (-0.6 dB for heavier 66t airframe) + 1.2 dB thrust/config penalty.",
    sourceDelta: -0.6,
    thrustDelta: 1.2,
    sources: () => [
      `Altitudes: LCY Consultation ${altitudeFigure()}. Distance: 6 dB per doubling (LCY Annex C p.41); SEL 10 log, standard rule. Air: 0.6 dB/1,000 ft, no source.`,
      "Source −0.6 dB: in EASA range (−0.8 to +1.1), pair not traced. Thrust +1.2 dB: assumed; evidence spans ~0 (LCY ANCS, Heathrow) to 2.5 dB (NASA 1968)."
    ]
  },
  {
    name: "vs E190-E2",
    desc: "A320neo 91.8 (est.) vs E190-E2 91.4 EPNdB approach (UK CAA TCDSN): +0.4 dB.",
    sourceDelta: 0.4,
    thrustDelta: 1.0
  }
];

const FONT_STACK = 'system-ui, -apple-system, "Segoe UI", sans-serif';
const ALTITUDE_SCALE_FT = 3400; // Headroom above the 3,000 ft level segment
const MIN_DB = -3;
const MAX_DB = 6;

// Series colours checked with the dataviz palette validator against white
const COLORS = {
  ink: "#16181d",
  inkSecondary: "#52555c",
  inkMuted: "#71747b",
  grid: "#ecece8",
  baseline: "#9a9c9f",
  crosshair: "#71747b",
  reference: "#d03b3b",
  current: "#2a78d6",
  proposed: "#eb6834",
  proposedTint: "rgba(235, 104, 52, 0.12)",
  net: "#6250d6",
  netTint: "rgba(98, 80, 214, 0.10)",
  component: "#71747b"
};

let activePreset = 2; // Default to EASA Empirical
let sourceSlider, thrustSlider;
let metricMode = "LAmax"; // "LAmax" (20log) or "SEL" (10log)
let probeNM = 2.0;        // Default highlight at 2.0 nm
let activeRunway = "27";

function distanceToX(nm, left, right) {
  const fraction = nm / 6.5;
  return activeRunway === "27"
    ? lerp(left, right, fraction)
    : lerp(right, left, fraction);
}

function waypoints() {
  return WAYPOINTS_BY_RUNWAY[activeRunway];
}

function altitudeFigure() {
  return activeRunway === "27" ? "Fig. 9, p.23" : "Fig. 8, p.22";
}

function usingAirportTable() {
  return activePreset >= 0 && PRESETS[activePreset].usesAirportTable === true;
}

// The airport's predicted A320neo minus E190 difference at nm, or null outside its 0.5–5 km table
function airportPrediction(nm) {
  const km = nm * KM_PER_NM;
  const table = LCY_E190_ARRIVALS[activeRunway];
  for (let i = 0; i < table.length - 1; i++) {
    if (km >= table[i][0] && km <= table[i + 1][0]) {
      const t = (km - table[i][0]) / (table[i + 1][0] - table[i][0]);
      return -lerp(table[i][1], table[i + 1][1], t);
    }
  }
  return null;
}

// Geometry + atmosphere in SEL, the metric the airport's table is published in
function selGeometryDB(nm) {
  const alts = getAltitudes(nm);
  return 10 * Math.log10(alts.curr / alts.prop) + ((alts.curr - alts.prop) / 1000) * 0.6;
}

// Not an airport figure: outside its table, continue from the nearest published value using altitude change only
function airportExtrapolation(nm) {
  const table = LCY_E190_ARRIVALS[activeRunway];
  const last = table[table.length - 1];
  const edge = nm * KM_PER_NM < (table[0][0] + last[0]) / 2 ? table[0] : last; // Nearest end of the table
  return -edge[1] + selGeometryDB(nm) - selGeometryDB(edge[0] / KM_PER_NM);
}

// Interpolate altitudes at any distance x (in nm)
function getAltitudes(nm) {
  nm = constrain(nm, 0.1, 6.5);
  const points = waypoints();

  for (let i = 0; i < points.length - 1; i++) {
    let w1 = points[i];
    let w2 = points[i + 1];
    if (nm >= w1.nm && nm <= w2.nm) {
      let t = (nm - w1.nm) / (w2.nm - w1.nm);
      let cAlt = lerp(w1.curr, w2.curr, t);
      let pAlt = lerp(w1.prop, w2.prop, t);
      return { curr: cAlt, prop: pAlt };
    }
  }
  // Level flight beyond the proposed top of descent
  const level = points[points.length - 1];
  return { curr: level.curr, prop: level.prop };
}

// Compute acoustic components at distance nm
function getAcoustics(nm) {
  let alts = getAltitudes(nm);
  let ratio = alts.curr / alts.prop;

  // 20*log10 for peak SPL (LAmax), 10*log10 for Sound Exposure Level (SEL)
  let coeff = (metricMode === "LAmax") ? 20.0 : 10.0;
  let geomDB = coeff * (Math.log(ratio) / Math.log(10));

  // Atmospheric absorption (~0.6 dB per 1000 ft for A-weighted aircraft spectra)
  let deltaFt = alts.curr - alts.prop;
  let atmDB = (deltaFt / 1000.0) * 0.6;

  // Operational thrust penalty applies when descending on the 4.49° glide slope
  const propTopOfDescent = waypoints()[waypoints().length - 1].nm;
  let sDelta = Number(sourceSlider.value);
  let tDelta = (nm < propTopOfDescent) ? Number(thrustSlider.value) : 0.0;

  let netDB = geomDB + atmDB + sDelta + tDelta;
  return {
    currAlt: alts.curr,
    propAlt: alts.prop,
    deltaFt: deltaFt,
    geomDB: geomDB,
    atmDB: atmDB,
    sourceDB: sDelta,
    thrustDB: tDelta,
    netDB: netDB
  };
}

// ---------------------------------------------------------------------------
// Page setup and controls (the controls themselves are in index.html)
// ---------------------------------------------------------------------------

function byId(id) {
  return document.getElementById(id);
}

function setup() {
  const box = byId("chart");
  const canvas = createCanvas(box.clientWidth, box.clientHeight);
  canvas.parent(box);
  textFont(FONT_STACK);
  noLoop(); // The charts only change when a control or the pointer does

  sourceSlider = byId("source-slider");
  thrustSlider = byId("thrust-slider");
  sourceSlider.min = SOURCE_SLIDER.min;
  sourceSlider.max = SOURCE_SLIDER.max;
  thrustSlider.min = THRUST_SLIDER.min;
  thrustSlider.max = THRUST_SLIDER.max;

  for (const slider of [sourceSlider, thrustSlider]) {
    slider.addEventListener("input", () => {
      activePreset = -1;
      refresh();
    });
  }

  placeBand(byId("band-e190"), SOURCE_RANGE_E190, SOURCE_SLIDER);
  placeBand(byId("band-e2"), SOURCE_RANGE_E2, SOURCE_SLIDER);
  placeBand(byId("band-thrust"), THRUST_RANGE, THRUST_SLIDER);

  PRESETS.forEach((preset, i) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = preset.name;
    button.addEventListener("click", () => applyPreset(i));
    byId("scenarios").appendChild(button);
  });

  document.querySelectorAll("[data-runway]").forEach(button => {
    button.addEventListener("click", () => {
      activeRunway = button.dataset.runway;
      refresh();
    });
  });

  document.querySelectorAll("[data-metric]").forEach(button => {
    button.addEventListener("click", () => {
      metricMode = button.dataset.metric;
      refresh();
    });
  });

  byId("fullscreen-btn").addEventListener("click", () => fullscreen(!fullscreen()));
  document.addEventListener("fullscreenchange", () => {
    byId("fullscreen-btn").textContent = document.fullscreenElement ? "Exit full screen" : "Full screen";
  });

  const element = canvas.elt;
  element.tabIndex = 0;
  element.setAttribute("role", "img");
  element.setAttribute("aria-label", "Flight profile and ground noise difference against distance from the runway threshold. Values at the selected distance are listed above the chart.");
  element.addEventListener("pointermove", movePointer);
  element.addEventListener("pointerdown", movePointer);
  element.addEventListener("keydown", moveProbeWithKeys);

  // The chart area changes size with the window and the sidebar's stacking
  new ResizeObserver(() => {
    if (box.clientWidth !== width || box.clientHeight !== height) {
      resizeCanvas(box.clientWidth, box.clientHeight);
    }
  }).observe(box);

  applyPreset(activePreset);
}

function placeBand(element, range, slider) {
  const toPercent = value => ((value - slider.min) / (slider.max - slider.min)) * 100;
  element.style.left = `${toPercent(range[0])}%`;
  element.style.width = `${toPercent(range[1]) - toPercent(range[0])}%`;
}

function applyPreset(idx) {
  activePreset = idx;
  sourceSlider.value = PRESETS[idx].sourceDelta;
  thrustSlider.value = PRESETS[idx].thrustDelta;
  refresh();
}

function refresh() {
  syncControls();
  redraw();
}

function setPressed(button, pressed) {
  button.setAttribute("aria-pressed", pressed ? "true" : "false");
}

function syncControls() {
  const airport = usingAirportTable();
  const preset = activePreset >= 0 ? PRESETS[activePreset] : null;

  [...byId("scenarios").children].forEach((button, i) => setPressed(button, i === activePreset));
  document.querySelectorAll("[data-runway]").forEach(button => {
    setPressed(button, button.dataset.runway === activeRunway);
  });
  document.querySelectorAll("[data-metric]").forEach(button => {
    setPressed(button, button.dataset.metric === currentMetric());
    button.disabled = airport;
  });

  byId("scenario-desc").textContent = preset ? preset.desc : "Custom values set with the sliders below.";
  byId("metric-hint").textContent = airport
    ? "The airport publishes SEL only."
    : (metricMode === "LAmax" ? "Loudest moment of the flyover (20 log)." : "Total sound energy of the flyover (10 log).");

  // The airport's single net figure already contains source and thrust
  byId("slider-note").hidden = !airport;
  byId("source-evidence").hidden = airport;
  byId("thrust-evidence").hidden = airport;
  for (const slider of [sourceSlider, thrustSlider]) {
    slider.disabled = airport;
    slider.closest(".field").classList.toggle("is-disabled", airport);
  }
  byId("source-value").textContent = airport ? "In LCY figure" : `${signed(Number(sourceSlider.value), 1)} dB`;
  byId("thrust-value").textContent = airport ? "In LCY figure" : `${signed(Number(thrustSlider.value), 1)} dB`;

  const sources = preset && preset.sources ? preset.sources() : null;
  byId("sources-section").hidden = !sources;
  byId("sources").replaceChildren(...(sources || []).map(line => {
    const paragraph = document.createElement("p");
    paragraph.textContent = line;
    return paragraph;
  }));

  document.body.classList.toggle("is-airport", airport);
}

function currentMetric() {
  return usingAirportTable() ? "SEL" : metricMode;
}

// Formats with an explicit sign and a true minus, never showing "-0.00"
function signed(value, decimals) {
  const fixed = Math.abs(value).toFixed(decimals);
  if (Number(fixed) === 0) return fixed;
  return (value > 0 ? "+" : "−") + fixed;
}

function feet(value) {
  return `${Math.round(value).toLocaleString("en-GB")} ft`;
}

// ---------------------------------------------------------------------------
// Pointer and keyboard
// ---------------------------------------------------------------------------

function movePointer(event) {
  const area = chartLayout();
  const rect = event.currentTarget.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  if (x < area.L || x > area.R || y < area.profile.top || y > area.noise.bottom) return;
  const fraction = activeRunway === "27"
    ? map(x, area.L, area.R, 0, 1)
    : map(x, area.R, area.L, 0, 1);
  probeNM = constrain(fraction * 6.5, 0.2, 6.5);
  redraw();
}

function moveProbeWithKeys(event) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  event.preventDefault();
  const step = event.shiftKey ? 0.5 : 0.05;
  const rightward = event.key === "ArrowRight";
  // RWY 09 is drawn with distance increasing to the left
  const further = activeRunway === "27" ? rightward : !rightward;
  probeNM = constrain(probeNM + (further ? step : -step), 0.2, 6.5);
  redraw();
}

// ---------------------------------------------------------------------------
// Chart layout, all in real canvas pixels
// ---------------------------------------------------------------------------

function chartLayout() {
  const compact = width < 620;
  const L = compact ? 48 : 64;
  const R = width - (compact ? 16 : 32);
  const stackedLegend = width < 700;

  const locations = locationLabels(L, R);
  const rowCount = Math.max(...locations.map(label => label.row)) + 1;

  const titleH = 22;
  const legendH = stackedLegend ? 40 : 20;
  const head = titleH + legendH + 8;
  const locationsH = 8 + rowCount * 17;
  const betweenCharts = 16;
  const axisH = 24;

  const plots = height - head * 2 - locationsH - betweenCharts - axisH;
  const profileH = plots * 0.55;

  const profileTop = head;
  const profileBottom = profileTop + profileH;
  const noiseHead = profileBottom + locationsH + betweenCharts;
  const noiseTop = noiseHead + head;
  const noiseBottom = height - axisH;

  return {
    compact,
    stackedLegend,
    L,
    R,
    locations,
    locationsTop: profileBottom + 8,
    profileHead: 0,
    noiseHead,
    profile: { top: profileTop, bottom: profileBottom },
    noise: { top: noiseTop, bottom: noiseBottom }
  };
}

// Place names along the distance axis, moved to a second row when they would touch
function locationLabels(L, R) {
  textSize(11);
  textStyle(NORMAL);
  const rowEnds = [];
  const labels = waypoints().map(w => {
    const halfWidth = textWidth(w.loc) / 2;
    const x = constrain(distanceToX(w.nm, L, R), halfWidth, width - halfWidth);
    return { text: w.loc, x, halfWidth };
  }).sort((a, b) => a.x - b.x);

  for (const label of labels) {
    let row = rowEnds.findIndex(end => label.x - label.halfWidth > end + 8);
    if (row < 0) row = rowEnds.length;
    rowEnds[row] = label.x + label.halfWidth;
    label.row = row;
  }
  return labels;
}

// ---------------------------------------------------------------------------
// Drawing
// ---------------------------------------------------------------------------

function draw() {
  background(255);
  strokeWeight(1);
  textStyle(NORMAL);

  const area = chartLayout();
  drawCrosshair(area);
  drawFlightProfile(area);
  drawNoiseGraph(area);
  drawProbeDots(area);
  updateReadout();
}

function chartTitle(label, y) {
  noStroke();
  fill(COLORS.ink);
  textSize(14);
  textStyle(BOLD);
  textAlign(LEFT, TOP);
  text(label, 0, y);
  textStyle(NORMAL);
}

// items: { label, color, dashed }. Text stays in ink; the swatch carries identity.
function drawLegend(items, area, y) {
  textSize(12);
  textAlign(LEFT, CENTER);
  let x = 0;
  items.forEach((item, i) => {
    const rowY = area.stackedLegend ? y + i * 18 : y;
    if (area.stackedLegend) x = 0;
    stroke(item.color);
    strokeWeight(2);
    if (item.dashed) drawingContext.setLineDash([4, 3]);
    line(x, rowY, x + 18, rowY);
    drawingContext.setLineDash([]);
    noStroke();
    strokeWeight(1);
    fill(COLORS.inkSecondary);
    text(item.label, x + 24, rowY);
    x += 24 + textWidth(item.label) + 20;
  });
}

function altitudeToY(ft, area) {
  return map(ft, 0, ALTITUDE_SCALE_FT, area.profile.bottom, area.profile.top);
}

function dbToY(db, area) {
  return map(constrain(db, MIN_DB, MAX_DB), MIN_DB, MAX_DB, area.noise.bottom, area.noise.top);
}

function traceAltitude(key, area) {
  beginShape();
  for (let nm = 0; nm <= 6.5; nm += 0.05) {
    vertex(distanceToX(nm, area.L, area.R), altitudeToY(getAltitudes(nm)[key], area));
  }
  vertex(distanceToX(6.5, area.L, area.R), altitudeToY(getAltitudes(6.5)[key], area));
  endShape();
}

function drawFlightProfile(area) {
  const { L, R, profile } = area;
  const points = waypoints();
  const propTOD = points[points.length - 1];
  const currTOD = points[points.length - 2];
  const levelFt = propTOD.curr.toLocaleString("en-GB");

  chartTitle(activeRunway === "27"
    ? "Flight profile: RWY 27, approach from the east"
    : "Flight profile: RWY 09, approach from the west", area.profileHead);
  drawLegend([
    { label: `Current 5.5° (${levelFt} ft top of descent at ${currTOD.nm} nm)`, color: COLORS.current },
    { label: `Proposed 4.49° (${levelFt} ft top of descent at ${propTOD.nm} nm)`, color: COLORS.proposed }
  ], area, area.profileHead + 32);

  // Altitude grid
  textSize(11);
  textAlign(RIGHT, CENTER);
  for (let alt = 0; alt <= 3000; alt += 500) {
    const y = altitudeToY(alt, area);
    stroke(alt === 0 ? COLORS.baseline : COLORS.grid);
    line(L, y, R, y);
    noStroke();
    fill(COLORS.inkMuted);
    text(area.compact ? alt.toLocaleString("en-GB") : `${alt.toLocaleString("en-GB")} ft`, L - 8, y);
  }

  // Waypoint guides, under the data
  stroke(COLORS.grid);
  for (const w of points) {
    const x = distanceToX(w.nm, L, R);
    line(x, altitudeToY(w.curr, area), x, profile.bottom);
  }

  // Shaded gap between the two slopes
  noStroke();
  fill(COLORS.proposedTint);
  beginShape();
  for (let nm = 0; nm <= 6.5; nm += 0.05) {
    vertex(distanceToX(nm, L, R), altitudeToY(getAltitudes(nm).curr, area));
  }
  for (let nm = 6.5; nm >= 0; nm -= 0.05) {
    vertex(distanceToX(nm, L, R), altitudeToY(getAltitudes(nm).prop, area));
  }
  endShape(CLOSE);

  noFill();
  strokeWeight(2);
  stroke(COLORS.current);
  traceAltitude("curr", area);
  stroke(COLORS.proposed);
  traceAltitude("prop", area);
  strokeWeight(1);

  // Waypoint markers and altitude labels; labels too close to the previous one are dropped
  let lastCurrX = null, lastPropX = null;
  textSize(11);
  for (const w of points) {
    const x = distanceToX(w.nm, L, R);
    const yc = altitudeToY(w.curr, area);
    const yp = altitudeToY(w.prop, area);
    drawMarker(x, yc, COLORS.current, 8);
    drawMarker(x, yp, COLORS.proposed, 8);
    if (w.nm === 0) continue;

    const labelFor = ft => area.compact ? ft.toLocaleString("en-GB") : `${ft.toLocaleString("en-GB")} ft`;
    noStroke();
    fill(COLORS.inkSecondary);
    // Set each label to the outer side of its slope: RWY 27 rises to the right, RWY 09 to the left
    const rising = activeRunway === "27";

    const currLabel = labelFor(w.curr);
    if (lastCurrX === null || Math.abs(x - lastCurrX) > textWidth(currLabel) + 4) {
      textAlign(rising ? RIGHT : LEFT, BOTTOM);
      haloText(currLabel, x + (rising ? 8 : -8), yc - 7);
      lastCurrX = x;
    }

    const propLabel = labelFor(w.prop);
    if (w.nm < propTOD.nm && (lastPropX === null || Math.abs(x - lastPropX) > textWidth(propLabel) + 4)) {
      textAlign(rising ? LEFT : RIGHT, TOP);
      haloText(propLabel, x + (rising ? -8 : 8), yp + 7);
      lastPropX = x;
    }
  }

  // Direct labels on the slopes, on the free stretch between two waypoints
  if (R - L > 640) {
    const nm = activeRunway === "27" ? 4.5 : 2.5;
    const x = distanceToX(nm, L, R);
    const lean = activeRunway === "27" ? 1 : -1; // Which way the slope rises across the screen
    const alts = getAltitudes(nm);
    noStroke();
    fill(COLORS.ink);
    textSize(12);
    textStyle(BOLD);
    textAlign(CENTER, CENTER);
    text("5.5°", x - lean * 20, altitudeToY(alts.curr, area) - 12);
    text("4.49°", x + lean * 22, altitudeToY(alts.prop, area) + 12);
    textStyle(NORMAL);
  }

  // Place names under the distance axis
  noStroke();
  fill(COLORS.inkSecondary);
  textSize(11);
  textAlign(CENTER, TOP);
  for (const label of area.locations) {
    text(label.text, label.x, area.locationsTop + label.row * 17);
  }
}

// Text with a white outline, so it stays readable over lines
function haloText(label, x, y) {
  stroke(255);
  strokeWeight(3);
  strokeJoin(ROUND);
  text(label, x, y);
  strokeWeight(1);
  noStroke();
}

function drawMarker(x, y, col, size) {
  stroke(255);
  strokeWeight(2);
  fill(col);
  circle(x, y, size + 2);
  strokeWeight(1);
  noStroke();
}

function drawNoiseGraph(area) {
  const { L, R, noise } = area;
  const airport = usingAirportTable();

  chartTitle(`Ground noise difference (Δ ${currentMetric()})`, area.noiseHead);
  drawLegend(airport
    ? [
      { label: "Airport prediction (0.5–5 km)", color: COLORS.net },
      { label: "Not predicted by the airport: estimate from altitude change only", color: COLORS.net, dashed: true }
    ]
    : [
      { label: "Total (altitude + atmosphere + source + thrust)", color: COLORS.net },
      { label: "Altitude + atmosphere only", color: COLORS.component, dashed: true }
    ], area, area.noiseHead + 32);

  // dB grid; every 3 dB when the plot is too short for every 1 dB
  const tickStep = (noise.bottom - noise.top) / (MAX_DB - MIN_DB) < 18 ? 3 : 1;
  textSize(11);
  textAlign(RIGHT, CENTER);
  for (let db = MIN_DB; db <= MAX_DB; db += tickStep) {
    const y = dbToY(db, area);
    if (db !== 0) {
      stroke(COLORS.grid);
      line(L, y, R, y);
    }
    noStroke();
    fill(db === 0 ? COLORS.ink : COLORS.inkMuted);
    text(`${db > 0 ? "+" : (db < 0 ? "−" : "")}${Math.abs(db)} dB`, L - 8, y);
  }

  // Which side of zero means what
  fill(COLORS.inkMuted);
  textSize(11);
  textAlign(activeRunway === "27" ? RIGHT : LEFT, TOP);
  const sideX = activeRunway === "27" ? R - 8 : L + 8;
  text("↑ Louder on 4.49°", sideX, noise.top + 4);
  textAlign(activeRunway === "27" ? RIGHT : LEFT, BOTTOM);
  text("↓ Quieter on 4.49°", sideX, noise.bottom - 4);

  // +3 dB reference
  const y3 = dbToY(3, area);
  stroke(COLORS.reference);
  drawingContext.setLineDash([4, 4]);
  line(L, y3, R, y3);
  drawingContext.setLineDash([]);
  noStroke();

  if (airport) {
    drawAirportCurve(area);
  } else {
    drawModelCurves(area);
  }

  fill(COLORS.inkSecondary);
  textSize(11);
  const refLabel = area.compact ? "+3 dB: double acoustic energy" : "+3 dB: double acoustic energy, clearly perceptible threshold";
  textAlign(activeRunway === "27" ? RIGHT : LEFT, BOTTOM);
  haloText(refLabel, activeRunway === "27" ? R - 8 : L + 8, y3 - 3);

  // Zero line and distance axis, over the fill
  stroke(COLORS.baseline);
  line(L, dbToY(0, area), R, dbToY(0, area));
  textSize(11);
  textAlign(CENTER, TOP);
  for (let nm = 0; nm <= 6; nm++) {
    const x = distanceToX(nm, L, R);
    stroke(COLORS.baseline);
    line(x, noise.bottom, x, noise.bottom + 4);
    noStroke();
    fill(COLORS.inkMuted);
    text(`${nm} nm`, x, noise.bottom + 7);
  }
  stroke(COLORS.grid);
  line(L, noise.bottom, R, noise.bottom);
  noStroke();
}

function drawAirportCurve(area) {
  const { L, R } = area;
  const table = LCY_E190_ARRIVALS[activeRunway];
  const firstNM = table[0][0] / KM_PER_NM;
  const lastNM = table[table.length - 1][0] / KM_PER_NM;

  noFill();
  stroke(COLORS.net);
  strokeWeight(2);

  // Dashed: distances the airport does not predict
  drawingContext.setLineDash([6, 5]);
  for (const [fromNM, toNM] of [[0.2, firstNM], [lastNM, 6.5]]) {
    beginShape();
    for (let nm = fromNM; nm < toNM; nm += 0.05) {
      vertex(distanceToX(nm, L, R), dbToY(airportExtrapolation(nm), area));
    }
    vertex(distanceToX(toNM, L, R), dbToY(airportExtrapolation(toNM), area));
    endShape();
  }
  drawingContext.setLineDash([]);

  // Solid: the airport's published figures
  strokeWeight(2.5);
  beginShape();
  for (const [km, e190Louder] of table) {
    vertex(distanceToX(km / KM_PER_NM, L, R), dbToY(-e190Louder, area));
  }
  endShape();
  strokeWeight(1);
}

function drawModelCurves(area) {
  const { L, R } = area;

  // Shaded area between the total and zero
  noStroke();
  fill(COLORS.netTint);
  beginShape();
  vertex(distanceToX(0.2, L, R), dbToY(0, area));
  for (let nm = 0.2; nm <= 6.5; nm += 0.05) {
    vertex(distanceToX(nm, L, R), dbToY(getAcoustics(nm).netDB, area));
  }
  vertex(distanceToX(6.5, L, R), dbToY(0, area));
  endShape(CLOSE);

  // Dashed: altitude and atmosphere alone
  noFill();
  stroke(COLORS.component);
  strokeWeight(2);
  drawingContext.setLineDash([5, 4]);
  beginShape();
  for (let nm = 0.2; nm <= 6.5; nm += 0.05) {
    const ac = getAcoustics(nm);
    vertex(distanceToX(nm, L, R), dbToY(ac.geomDB + ac.atmDB, area));
  }
  endShape();
  drawingContext.setLineDash([]);

  // Solid: the total
  stroke(COLORS.net);
  strokeWeight(2.5);
  beginShape();
  for (let nm = 0.2; nm <= 6.5; nm += 0.05) {
    vertex(distanceToX(nm, L, R), dbToY(getAcoustics(nm).netDB, area));
  }
  endShape();
  strokeWeight(1);
}

// The airport's figure at nm, or its estimate outside the table; null means use the model's total
function probeAirportValues(nm) {
  if (!usingAirportTable()) return null;
  const predicted = airportPrediction(nm);
  return predicted === null
    ? { predicted: false, db: airportExtrapolation(nm) }
    : { predicted: true, db: predicted };
}

function drawCrosshair(area) {
  const x = distanceToX(probeNM, area.L, area.R);
  stroke(COLORS.crosshair);
  line(x, area.profile.top, x, area.profile.bottom);
  line(x, area.noise.top, x, area.noise.bottom);
  noStroke();
}

function drawProbeDots(area) {
  const x = distanceToX(probeNM, area.L, area.R);
  const ac = getAcoustics(probeNM);
  const airport = probeAirportValues(probeNM);

  drawProbeDot(x, altitudeToY(ac.currAlt, area), COLORS.current);
  drawProbeDot(x, altitudeToY(ac.propAlt, area), COLORS.proposed);
  drawProbeDot(x, dbToY(airport ? airport.db : ac.netDB, area), COLORS.net);
}

function drawProbeDot(x, y, col) {
  stroke(col);
  strokeWeight(2.5);
  fill(255);
  circle(x, y, 10);
  strokeWeight(1);
  noStroke();
}

function updateReadout() {
  const ac = getAcoustics(probeNM);
  const airport = probeAirportValues(probeNM);
  const db = airport ? airport.db : ac.netDB;

  byId("r-distance").textContent = `${probeNM.toFixed(2)} nm`;
  byId("r-curr").textContent = feet(ac.currAlt);
  byId("r-prop").textContent = feet(ac.propAlt);
  byId("r-drop").textContent = `${signed(-Math.round(ac.deltaFt), 0)} ft`;
  byId("r-geom").textContent = `${signed(ac.geomDB + ac.atmDB, 2)} dB`;
  byId("r-source").textContent = `${signed(ac.sourceDB + ac.thrustDB, 2)} dB`;

  byId("r-net-label").textContent = !airport
    ? "Net ground difference"
    : (airport.predicted ? "Airport prediction, A320neo vs E190" : "Not predicted by the airport: estimate");
  byId("r-net").textContent = `${signed(db, 2)} dB ${currentMetric()}`;

  const chip = byId("r-chip");
  const louder = db > 0.2, quieter = db < -0.2;
  chip.textContent = louder ? "▲ Louder" : (quieter ? "▼ Quieter" : "≈ No change");
  chip.className = `chip${louder ? " is-louder" : ""}${quieter ? " is-quieter" : ""}`;
}

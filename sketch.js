/**
 * London City approach noise model: page controls and charts.
 * The data and calculations are in model.js; the controls are in index.html.
 */
const SOURCE_SLIDER = { min: -4.0, max: 3.0 };
const THRUST_SLIDER = { min: 0.0, max: 4.0 };

const ALTITUDE_AND_AIR_NOTE = "Distance: 6 dB per doubling (Annex C p.41). SEL 10 log: rule of thumb, no source; the airport's A320neo levels fall about 14.5 log with height. Air: 0.6 dB/1,000 ft, no source.";

const PRESETS = [
  {
    name: "Geometry",
    desc: "Altitude and air only, as if the same aircraft flew both slopes. Not a real scenario: only the A320neo is planned to use 4.49°.",
    sameAircraft: true,
    sourceDelta: () => 0.0,
    thrustDelta: 0.0,
    sources: () => [
      `Same aircraft, thrust, speed and flaps on both slopes. Altitudes: LCY Consultation ${altitudeFigure()} (${activeRunway === "27" ? "its 1 nm label of 574 ft corrected to 547 ft" : "its 1,692 ft label replaced by slope value 1,656 ft"}). Listener directly below path, flat ground.`,
      ALTITUDE_AND_AIR_NOTE
    ]
  },
  {
    name: "Airport tables",
    desc: "LCY consultation Figs. 17–18: A320neo at 4.49° against each other type at 5.5° (SEL, net). Published for 0.5–5 km only.",
    usesAirportTable: true,
    sourceDelta: () => 0.0, // Not used: the airport publishes one net figure, which already includes source and thrust
    thrustDelta: 0.0,
    sources: () => [
      "AEDT 3g model, not measured. A320neo: unadjusted AEDT data on LCY profile at 4.49° (Annex C pp.8, 12). Thrust: estimated within flight profiles, no value published (p.7). Flap, gear, engine variant, weight, weather: none stated.",
      "E190 and A220 differ by exactly 3.0 dB at every point: both are 737-500 data, adjusted +1.5 and −1.5 dB (Annex C p.10). Their change with distance reflects that shared data, not necessarily either aircraft."
    ]
  },
  {
    name: "Illustrative",
    desc: "Assumed values against the E190, not a finding: −0.6 dB from certificates plus 1.2 dB of assumed thrust.",
    compare: "E190",
    sourceDelta: () => -0.6,
    thrustDelta: 1.2,
    sources: () => [
      `Altitudes: LCY Consultation ${altitudeFigure()}. ${ALTITUDE_AND_AIR_NOTE}`,
      "Source −0.6 dB: within certificates (−0.8 to +1.1, EPNdB at 3° and maximum landing mass), pair not traced; measured arrivals at Reagan National give about −2 dB. Thrust +1.2 dB: assumed."
    ]
  },
  {
    name: "Fit to E190-E2",
    desc: "A constant source difference fitted to the airport's E190-E2 column in SEL. It restates the airport's model and is not independent evidence.",
    compare: "E190-E2",
    sourceDelta: () => Math.round(NoiseModel.fittedSourceDB(activeRunway, "E190-E2") * 10) / 10,
    thrustDelta: 0.0, // The fit is net, so any thrust effect is already inside the source figure
    sources: () => [
      "Source: average of the airport's A320neo minus E190-E2 figure, less altitude and air, across 0.5–5 km; it fits within 0.6 dB. Thrust is 0 because the fit already contains it.",
      "Certificates give +0.6 to +1.5 dB: A320neo 92.0–92.9 vs E190-E2 91.4 EPNdB (EASA). Figures: Consultation pp.30–31."
    ]
  }
];

const FONT_STACK = 'system-ui, -apple-system, "Segoe UI", sans-serif';
const ALTITUDE_SCALE_FT = 3400; // Headroom above the 3,000 ft level segment
const MIN_DB = -3; // The noise chart grows beyond this range when the data needs it
const MAX_DB = 6;
const SAMPLE_NM = 0.05;
const FIRST_NOISE_NM = 0.2;

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
  netTint: "rgba(98, 80, 214, 0.13)",
  airport: "#199e70",
  component: "#71747b"
};

let activePreset = 0;       // Geometry: the only scenario with no assumed aircraft difference
let sourceSlider, thrustSlider;
let metricMode = "SEL";     // "LAmax" (20 log) or "SEL" (10 log). SEL matches the airport's tables.
let compareAircraft = "E195-E2"; // The largest type in the airport's 2038 forecast without the change
let probeNM = 2.0;          // Default highlight at 2.0 nm
let activeRunway = "27";

function distanceToX(nm, left, right) {
  const fraction = nm / NoiseModel.MAX_NM;
  return activeRunway === "27"
    ? lerp(left, right, fraction)
    : lerp(right, left, fraction);
}

function waypoints() {
  return NoiseModel.WAYPOINTS[activeRunway];
}

function altitudeFigure() {
  return activeRunway === "27" ? "Fig. 9, p.23" : "Fig. 8, p.22";
}

function currentPreset() {
  return activePreset >= 0 ? PRESETS[activePreset] : null;
}

function usingAirportTable() {
  const preset = currentPreset();
  return preset !== null && preset.usesAirportTable === true;
}

function isSameAircraft() {
  const preset = currentPreset();
  return preset !== null && preset.sameAircraft === true;
}

function getAcoustics(nm) {
  return NoiseModel.acoustics(activeRunway, nm, {
    metric: metricMode,
    sourceDB: Number(sourceSlider.value),
    thrustDB: Number(thrustSlider.value)
  });
}

function getEvidenceRange(nm) {
  return NoiseModel.evidenceRange(activeRunway, nm, {
    metric: metricMode,
    sourceRange: isSameAircraft() ? [0, 0] : NoiseModel.SOURCE_RANGES[compareAircraft].range,
    thrustRange: NoiseModel.THRUST_RANGE
  });
}

// Distances from one end to the other at the sampling step, always including both ends
function samplesNM(from, to) {
  const count = Math.round((to - from) / SAMPLE_NM);
  return Array.from({ length: count + 1 }, (_, i) => i === count ? to : from + i * SAMPLE_NM);
}

function airportTableNM() {
  return NoiseModel.ARRIVAL_KM.map(km => km / NoiseModel.KM_PER_NM);
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

  placeBand(byId("band-thrust"), NoiseModel.THRUST_RANGE, THRUST_SLIDER);

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
      if (currentPreset()) setSliders(currentPreset()); // A fitted source differs by runway
      refresh();
    });
  });

  document.querySelectorAll("[data-metric]").forEach(button => {
    button.addEventListener("click", () => {
      metricMode = button.dataset.metric;
      refresh();
    });
  });

  document.querySelectorAll("[data-compare]").forEach(button => {
    button.addEventListener("click", () => {
      compareAircraft = button.dataset.compare;
      // A scenario tied to one aircraft no longer describes what is shown
      if (currentPreset() && currentPreset().compare) activePreset = -1;
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

function setSliders(preset) {
  sourceSlider.value = preset.sourceDelta();
  thrustSlider.value = preset.thrustDelta;
}

function applyPreset(idx) {
  activePreset = idx;
  setSliders(PRESETS[idx]);
  if (PRESETS[idx].compare) compareAircraft = PRESETS[idx].compare;
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
  const preset = currentPreset();

  [...byId("scenarios").children].forEach((button, i) => setPressed(button, i === activePreset));
  document.querySelectorAll("[data-runway]").forEach(button => {
    setPressed(button, button.dataset.runway === activeRunway);
  });
  document.querySelectorAll("[data-metric]").forEach(button => {
    setPressed(button, button.dataset.metric === currentMetric());
    button.disabled = airport;
  });

  document.querySelectorAll("[data-compare]").forEach(button => {
    setPressed(button, button.dataset.compare === compareAircraft);
  });
  const flights = NoiseModel.FLIGHTS_WITHOUT_CHANGE[compareAircraft];
  byId("compare-hint").textContent = `Forecast without the change: ${flights[2027].toLocaleString("en-GB")} flights in 2027, ${flights[2038].toLocaleString("en-GB")} in 2038 (Fig. 3).`;

  const evidence = NoiseModel.SOURCE_RANGES[compareAircraft];
  placeBand(byId("band-source"), evidence.range, SOURCE_SLIDER);
  byId("source-evidence-text").textContent = evidence.text;

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
  probeNM = constrain(fraction * NoiseModel.MAX_NM, FIRST_NOISE_NM, NoiseModel.MAX_NM);
  redraw();
}

function moveProbeWithKeys(event) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  event.preventDefault();
  const step = event.shiftKey ? 0.5 : 0.05;
  const rightward = event.key === "ArrowRight";
  // RWY 09 is drawn with distance increasing to the left
  const further = activeRunway === "27" ? rightward : !rightward;
  probeNM = constrain(probeNM + (further ? step : -step), FIRST_NOISE_NM, NoiseModel.MAX_NM);
  redraw();
}

// ---------------------------------------------------------------------------
// Chart layout, all in real canvas pixels
// ---------------------------------------------------------------------------

function chartLayout() {
  const compact = width < 620;
  const L = compact ? 48 : 64;
  const R = width - (compact ? 16 : 32);

  const locations = locationLabels(L, R);
  const rowCount = Math.max(...locations.map(label => label.row)) + 1;
  const profileLegend = placeLegend(profileLegendItems());
  const noiseLegend = placeLegend(noiseLegendItems());

  const headHeight = legend => 22 + (Math.max(...legend.map(item => item.row)) + 1) * 18 + 10;
  const profileHeadH = headHeight(profileLegend);
  const noiseHeadH = headHeight(noiseLegend);
  const locationsH = 8 + rowCount * 17;
  const betweenCharts = 16;
  const axisH = 24;

  const plots = height - profileHeadH - noiseHeadH - locationsH - betweenCharts - axisH;
  const profileH = plots * 0.55;

  const profileTop = profileHeadH;
  const profileBottom = profileTop + profileH;
  const noiseHead = profileBottom + locationsH + betweenCharts;
  const noiseTop = noiseHead + noiseHeadH;
  const noiseBottom = height - axisH;

  return {
    compact,
    L,
    R,
    locations,
    profileLegend,
    noiseLegend,
    locationsTop: profileBottom + 8,
    profileHead: 0,
    noiseHead,
    profile: { top: profileTop, bottom: profileBottom },
    noise: { top: noiseTop, bottom: noiseBottom, ...noiseDomain() }
  };
}

// The noise chart's dB range: the usual range, extended to whole dB when anything drawn goes beyond it
function noiseDomain() {
  const values = [MIN_DB, MAX_DB];
  if (usingAirportTable()) {
    for (const aircraft of NoiseModel.AIRCRAFT) {
      values.push(...NoiseModel.ARRIVALS[activeRunway][aircraft].map(value => -value));
    }
  } else {
    for (const nm of samplesNM(FIRST_NOISE_NM, NoiseModel.MAX_NM)) {
      const range = getEvidenceRange(nm);
      values.push(getAcoustics(nm).netDB, range.low, range.high);
    }
  }
  return { minDB: Math.floor(Math.min(...values)), maxDB: Math.ceil(Math.max(...values)) };
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

function profileLegendItems() {
  const points = waypoints();
  const propTOD = points[points.length - 1];
  const currTOD = points[points.length - 2];
  const levelFt = propTOD.curr.toLocaleString("en-GB");
  return [
    { label: `Current 5.5° (${levelFt} ft top of descent at ${currTOD.nm} nm)`, color: COLORS.current },
    { label: `Proposed 4.49° (${levelFt} ft top of descent at ${propTOD.nm} nm)`, color: COLORS.proposed }
  ];
}

function hasAdjustments() {
  return Number(sourceSlider.value) !== 0 || Number(thrustSlider.value) !== 0;
}

function noiseLegendItems() {
  if (usingAirportTable()) {
    return [
      { label: `Airport table: A320neo vs ${compareAircraft}`, color: COLORS.airport },
      { label: "Airport table: other aircraft", color: COLORS.component }
    ];
  }
  const items = hasAdjustments()
    ? [
      { label: "Total (altitude + atmosphere + source + thrust)", color: COLORS.net },
      { label: "Altitude + atmosphere only", color: COLORS.component, dashed: true }
    ]
    : [{ label: "Altitude + atmosphere", color: COLORS.net }];
  items.push({
    label: isSameAircraft() ? "Range if thrust adds 0 to 2.5 dB" : "Evidence range, source + thrust",
    color: COLORS.netTint,
    band: true
  });
  items.push({
    label: `Airport table vs ${compareAircraft} (${metricMode === "SEL" ? "SEL" : "SEL, not LAmax"})`,
    color: COLORS.airport
  });
  return items;
}

// Gives each legend item a position, wrapping to a new row when it wouldn't fit
function placeLegend(items) {
  textSize(12);
  textStyle(NORMAL);
  let x = 0, row = 0;
  return items.map(item => {
    const itemWidth = 24 + textWidth(item.label);
    if (x > 0 && x + itemWidth > width) {
      x = 0;
      row++;
    }
    const placed = { ...item, x, row };
    x += itemWidth + 20;
    return placed;
  });
}

// Text stays in ink; the swatch carries identity
function drawLegend(items, y) {
  textSize(12);
  textAlign(LEFT, CENTER);
  for (const item of items) {
    const rowY = y + item.row * 18;
    if (item.band) {
      noStroke();
      fill(item.color);
      rect(item.x, rowY - 5, 18, 10, 2);
    } else {
      stroke(item.color);
      strokeWeight(2);
      if (item.dashed) drawingContext.setLineDash([4, 3]);
      line(item.x, rowY, item.x + 18, rowY);
      drawingContext.setLineDash([]);
    }
    noStroke();
    strokeWeight(1);
    fill(COLORS.inkSecondary);
    text(item.label, item.x + 24, rowY);
  }
}

function altitudeToY(ft, area) {
  return map(ft, 0, ALTITUDE_SCALE_FT, area.profile.bottom, area.profile.top);
}

function dbToY(db, area) {
  return map(db, area.noise.minDB, area.noise.maxDB, area.noise.bottom, area.noise.top);
}

function traceAltitude(key, area) {
  beginShape();
  for (const nm of samplesNM(0, NoiseModel.MAX_NM)) {
    vertex(distanceToX(nm, area.L, area.R), altitudeToY(NoiseModel.altitudes(activeRunway, nm)[key], area));
  }
  endShape();
}

function drawFlightProfile(area) {
  const { L, R, profile } = area;
  const points = waypoints();
  const propTOD = points[points.length - 1];

  chartTitle(activeRunway === "27"
    ? "Flight profile: RWY 27, approach from the east"
    : "Flight profile: RWY 09, approach from the west", area.profileHead);
  drawLegend(area.profileLegend, area.profileHead + 32);

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
  const distances = samplesNM(0, NoiseModel.MAX_NM);
  for (const nm of distances) {
    vertex(distanceToX(nm, L, R), altitudeToY(NoiseModel.altitudes(activeRunway, nm).curr, area));
  }
  for (const nm of [...distances].reverse()) {
    vertex(distanceToX(nm, L, R), altitudeToY(NoiseModel.altitudes(activeRunway, nm).prop, area));
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
    const alts = NoiseModel.altitudes(activeRunway, nm);
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
  const leftAligned = activeRunway === "09"; // Keeps notes over the far end of the chart, away from the runway

  chartTitle(`Ground noise difference (Δ ${currentMetric()})`, area.noiseHead);
  drawLegend(area.noiseLegend, area.noiseHead + 32);

  // dB grid; every 3 dB when the plot is too short for every 1 dB
  const tickStep = (noise.bottom - noise.top) / (noise.maxDB - noise.minDB) < 18 ? 3 : 1;
  textSize(11);
  textAlign(RIGHT, CENTER);
  for (let db = Math.ceil(noise.minDB / tickStep) * tickStep; db <= noise.maxDB; db += tickStep) {
    const y = dbToY(db, area);
    if (db !== 0) {
      stroke(COLORS.grid);
      line(L, y, R, y);
    }
    noStroke();
    fill(db === 0 ? COLORS.ink : COLORS.inkMuted);
    text(`${db > 0 ? "+" : (db < 0 ? "−" : "")}${Math.abs(db)} dB`, L - 8, y);
  }

  // Which side of zero means what. Only Geometry is a pure slope effect; the rest also change the aircraft.
  const subject = isSameAircraft() ? "on 4.49°" : "A320neo at 4.49°";
  const sideX = leftAligned ? L + 8 : R - 8;
  fill(COLORS.inkMuted);
  textSize(11);
  textAlign(leftAligned ? LEFT : RIGHT, TOP);
  text(isSameAircraft() ? `↑ Louder ${subject}` : `↑ ${subject} louder`, sideX, noise.top + 4);
  textAlign(leftAligned ? LEFT : RIGHT, BOTTOM);
  text(isSameAircraft() ? `↓ Quieter ${subject}` : `↓ ${subject} quieter`, sideX, noise.bottom - 4);

  // +3 dB reference
  const y3 = dbToY(3, area);
  stroke(COLORS.reference);
  drawingContext.setLineDash([4, 4]);
  line(L, y3, R, y3);
  drawingContext.setLineDash([]);
  noStroke();

  if (usingAirportTable()) {
    drawAirportTables(area);
  } else {
    drawModelCurves(area);
    drawAirportCurve(compareAircraft, area, true);
    drawAirportCurveLabels([compareAircraft], area);
  }

  fill(COLORS.inkSecondary);
  textSize(11);
  const refLabel = area.compact ? "+3 dB: double acoustic energy" : "+3 dB: double acoustic energy, the airport's \"noticeable\" level";
  textAlign(leftAligned ? LEFT : RIGHT, BOTTOM);
  haloText(refLabel, sideX, y3 - 3);

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

function drawAirportTables(area) {
  const others = NoiseModel.AIRCRAFT.filter(aircraft => aircraft !== compareAircraft);
  for (const aircraft of others) drawAirportCurve(aircraft, area, false);
  drawAirportCurve(compareAircraft, area, true);
  drawAirportCurveLabels(NoiseModel.AIRCRAFT, area);
}

// Only the published points are joined: the airport gives no figures outside 0.5–5 km
function drawAirportCurve(aircraft, area, emphasised) {
  const { L, R } = area;
  const distances = airportTableNM();
  const heights = NoiseModel.ARRIVALS[activeRunway][aircraft].map(value => dbToY(-value, area));

  noFill();
  stroke(emphasised ? COLORS.airport : COLORS.component);
  strokeWeight(emphasised ? 2.5 : 1.5);
  beginShape();
  distances.forEach((nm, i) => vertex(distanceToX(nm, L, R), heights[i]));
  endShape();
  strokeWeight(1);

  if (emphasised) {
    distances.forEach((nm, i) => drawMarker(distanceToX(nm, L, R), heights[i], COLORS.airport, 6));
  }
}

// Names beside the 5 km end of each curve, spread out where the curves end close together
function drawAirportCurveLabels(aircraftList, area) {
  const { L, R } = area;
  const lastIndex = NoiseModel.ARRIVAL_KM.length - 1;
  const x = distanceToX(airportTableNM()[lastIndex], L, R) + (activeRunway === "27" ? 10 : -10);
  // A lone label goes above its curve, clear of the model lines that continue past 5 km
  const lift = aircraftList.length === 1 ? 11 : 0;
  const lineHeight = 14;

  const labels = aircraftList
    .map(aircraft => ({ aircraft, y: dbToY(-NoiseModel.ARRIVALS[activeRunway][aircraft][lastIndex], area) }))
    .sort((a, b) => a.y - b.y);
  labels.forEach((label, i) => {
    if (i > 0) label.y = Math.max(label.y, labels[i - 1].y + lineHeight);
  });

  textSize(11);
  textAlign(activeRunway === "27" ? LEFT : RIGHT, CENTER);
  for (const label of labels) {
    textStyle(label.aircraft === compareAircraft ? BOLD : NORMAL);
    fill(label.aircraft === compareAircraft ? COLORS.ink : COLORS.inkSecondary);
    haloText(label.aircraft, x, label.y - lift);
  }
  textStyle(NORMAL);
}

function drawModelCurves(area) {
  const { L, R } = area;
  const distances = samplesNM(FIRST_NOISE_NM, NoiseModel.MAX_NM);

  // Band: what the evidence ranges allow at each distance
  const ranges = distances.map(getEvidenceRange);
  noStroke();
  fill(COLORS.netTint);
  beginShape();
  distances.forEach((nm, i) => vertex(distanceToX(nm, L, R), dbToY(ranges[i].high, area)));
  for (let i = distances.length - 1; i >= 0; i--) {
    vertex(distanceToX(distances[i], L, R), dbToY(ranges[i].low, area));
  }
  endShape(CLOSE);

  noFill();
  if (hasAdjustments()) {
    // Dashed: altitude and atmosphere alone
    stroke(COLORS.component);
    strokeWeight(2);
    drawingContext.setLineDash([5, 4]);
    beginShape();
    for (const nm of distances) {
      vertex(distanceToX(nm, L, R), dbToY(getAcoustics(nm).geometryDB, area));
    }
    endShape();
    drawingContext.setLineDash([]);
  }

  // Solid: the total
  stroke(COLORS.net);
  strokeWeight(2.5);
  beginShape();
  for (const nm of distances) {
    vertex(distanceToX(nm, L, R), dbToY(getAcoustics(nm).netDB, area));
  }
  endShape();
  strokeWeight(1);
}

function airportFigureAtProbe() {
  return NoiseModel.airportDifference(activeRunway, compareAircraft, probeNM);
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
  const airport = airportFigureAtProbe();

  drawProbeDot(x, altitudeToY(ac.currAlt, area), COLORS.current);
  drawProbeDot(x, altitudeToY(ac.propAlt, area), COLORS.proposed);
  if (!usingAirportTable()) drawProbeDot(x, dbToY(ac.netDB, area), COLORS.net);
  if (airport !== null) drawProbeDot(x, dbToY(airport, area), COLORS.airport);
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
  const airport = airportFigureAtProbe();
  const airportText = airport === null ? "None here" : `${signed(airport, 1)} dB`;

  byId("r-distance").textContent = `${probeNM.toFixed(2)} nm`;
  byId("r-curr").textContent = feet(ac.currAlt);
  byId("r-prop").textContent = feet(ac.propAlt);
  byId("r-drop").textContent = `${signed(-Math.round(ac.deltaFt), 0)} ft`;
  byId("r-geom").textContent = `${signed(ac.geometryDB, 1)} dB`;
  byId("r-source").textContent = `${signed(ac.sourceDB + ac.thrustDB, 1)} dB`;
  byId("r-airport-label").textContent = `Airport vs ${compareAircraft} (SEL)`;
  byId("r-airport").textContent = airportText;

  if (usingAirportTable()) {
    byId("r-net-label").textContent = airport === null
      ? "The airport publishes figures for 0.5–5 km only"
      : `Airport table, A320neo vs ${compareAircraft}`;
    byId("r-net").textContent = airport === null ? "No figure" : `${signed(airport, 1)} dB SEL`;
    if (airport === null) setChip("", "");
    else setChip(...directionOf(airport, airport));
    return;
  }

  const range = getEvidenceRange(probeNM);
  byId("r-range").textContent = `${signed(range.low, 1)} to ${signed(range.high, 1)} dB`;
  byId("r-net-label").textContent = isSameAircraft() ? "Net ground difference, same aircraft" : `Net ground difference, A320neo vs ${compareAircraft}`;
  byId("r-net").textContent = `${signed(ac.netDB, 1)} dB ${metricMode}`;
  if (ac.netDB < range.low || ac.netDB > range.high) setChip("Outside evidence range", "");
  else setChip(...directionOf(range.low, range.high));
}

// The direction is only stated when the whole range agrees on it
function directionOf(low, high) {
  if (low > 0.2) return ["▲ Louder", " is-louder"];
  if (high < -0.2) return ["▼ Quieter", " is-quieter"];
  if (low >= -0.2 && high <= 0.2) return ["≈ No change", ""];
  return ["Direction uncertain", ""];
}

function setChip(label, modifier) {
  const chip = byId("r-chip");
  chip.textContent = label;
  chip.hidden = label === "";
  chip.className = `chip${modifier}`;
}

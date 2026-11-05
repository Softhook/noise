/**
 * The two charts, drawn with p5 in real canvas pixels: the flight profile above the noise difference.
 */

const FONT_STACK = 'system-ui, -apple-system, "Segoe UI", sans-serif';
const ALTITUDE_SCALE_FT = 3400; // Headroom above the 3,000 ft level segment
const DEFAULT_MIN_DB = -4;
const DEFAULT_MAX_DB = 6;
const SAMPLE_STEPS = 130; // Sample intervals per curve
const CANVAS_DESCRIPTION = "Flight profile and ground noise difference against distance from the runway threshold. Values at the selected distance are listed above the chart. Press Enter to pin or unpin the selected distance.";

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
  netRange: "rgba(98, 80, 214, 0.18)",
  component: "#71747b"
};

// ---------------------------------------------------------------------------
// Layout and scales
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
  const noiseLegendH = stackedLegend ? 76 : 20; // Up to four rows when stacked
  const head = titleH + legendH + 8;
  const noiseHeadH = titleH + noiseLegendH + 8;
  const locationsH = 8 + rowCount * 17;
  const betweenCharts = 16;
  const axisH = 24;

  const plots = height - head - noiseHeadH - locationsH - betweenCharts - axisH;
  const profileBottom = head + plots * 0.55;
  const noiseHead = profileBottom + locationsH + betweenCharts;

  return {
    compact,
    stackedLegend,
    L,
    R,
    bounds: noiseBounds(),
    locations,
    locationsTop: profileBottom + 8,
    profileHead: 0,
    noiseHead,
    profile: { top: head, bottom: profileBottom },
    noise: { top: noiseHead + noiseHeadH, bottom: height - axisH }
  };
}

// The dB scale, widened in 2 dB steps when the curves and evidence range need more room
function noiseBounds() {
  let minDB = DEFAULT_MIN_DB;
  let maxDB = DEFAULT_MAX_DB;
  if (usingAirportTable()) return { minDB, maxDB };

  let curveMin = 0;
  let curveMax = 0;
  for (const nm of evidenceSamples()) {
    const ac = getAcoustics(nm);
    const heightAir = ac.geomDB + ac.atmDB;
    const range = hasAdjustments() ? evidenceRangeAt(nm) : { low: ac.netDB, high: ac.netDB };
    curveMin = Math.min(curveMin, ac.netDB, heightAir, range.low);
    curveMax = Math.max(curveMax, ac.netDB, heightAir, range.high);
  }
  if (curveMin < minDB + 0.2) minDB = Math.floor((curveMin - 0.3) / 2) * 2;
  if (curveMax > maxDB - 0.2) maxDB = Math.ceil((curveMax + 0.3) / 2) * 2;
  return { minDB, maxDB };
}

// Place names along the distance axis, moved to a second row when they would touch
function locationLabels(L, R) {
  textSize(11);
  textStyle(NORMAL);
  const rowEnds = [];
  const labels = waypoints().map(w => {
    const halfWidth = textWidth(w.loc) / 2;
    const x = constrain(distanceToX(w.nm, { L, R }), halfWidth, width - halfWidth);
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

// RWY 09 is drawn with distance increasing to the left
function distanceToX(nm, { L, R }) {
  const fraction = nm / CHART_MAX_NM;
  return state.runway === "27" ? lerp(L, R, fraction) : lerp(R, L, fraction);
}

function xToDistance(x, { L, R }) {
  const fraction = state.runway === "27" ? map(x, L, R, 0, 1) : map(x, R, L, 0, 1);
  return constrain(fraction * CHART_MAX_NM, 0, CHART_MAX_NM);
}

function altitudeToY(ft, area) {
  return map(ft, 0, ALTITUDE_SCALE_FT, area.profile.bottom, area.profile.top);
}

function dbToY(db, area) {
  const { minDB, maxDB } = area.bounds;
  return map(constrain(db, minDB, maxDB), minDB, maxDB, area.noise.bottom, area.noise.top);
}

// Evenly spaced distances out to the end of the chart
function distanceSamples(fromNM = 0) {
  return Array.from({ length: SAMPLE_STEPS + 1 }, (_, i) => lerp(fromNM, CHART_MAX_NM, i / SAMPLE_STEPS));
}

// Includes both sides of each top-of-descent step, so the evidence band aligns with the waypoint guides
function evidenceSamples() {
  const currTOD = currentTopOfDescent().nm;
  const propTOD = proposedTopOfDescent().nm;
  const steps = [currTOD, currTOD + NM_TOLERANCE, propTOD - NM_TOLERANCE, propTOD]
    .filter(nm => nm >= MIN_MODEL_NM && nm <= CHART_MAX_NM);
  return [...distanceSamples(MIN_MODEL_NM), ...steps].sort((a, b) => a - b);
}

// ---------------------------------------------------------------------------
// Drawing helpers
// ---------------------------------------------------------------------------

function vertices(points) {
  for (const [x, y] of points) vertex(x, y);
}

function drawPolyline(points) {
  beginShape();
  vertices(points);
  endShape();
}

function drawPolygon(points) {
  beginShape();
  vertices(points);
  endShape(CLOSE);
}

function withDash(pattern, drawDashed) {
  drawingContext.setLineDash(pattern);
  drawDashed();
  drawingContext.setLineDash([]);
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

// items: { label, color, dash, band }. Text stays in ink; the swatch carries identity.
function drawLegend(items, area, y) {
  textSize(12);
  textAlign(LEFT, CENTER);
  let x = 0;
  items.forEach((item, i) => {
    const rowY = area.stackedLegend ? y + i * 18 : y;
    if (area.stackedLegend) x = 0;
    if (item.band) {
      noStroke();
      fill(item.color);
      rect(x, rowY - 5, 18, 10);
    } else {
      stroke(item.color);
      strokeWeight(2);
      withDash(item.dash ?? [], () => line(x, rowY, x + 18, rowY));
    }
    noStroke();
    strokeWeight(1);
    fill(COLORS.inkSecondary);
    text(item.label, x + 24, rowY);
    x += 24 + textWidth(item.label) + 20;
  });
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

function drawMarker(x, y, color, size) {
  stroke(255);
  strokeWeight(2);
  fill(color);
  circle(x, y, size + 2);
  strokeWeight(1);
  noStroke();
}

// ---------------------------------------------------------------------------
// Whole frame
// ---------------------------------------------------------------------------

function drawCharts() {
  background(255);
  strokeWeight(1);
  textStyle(NORMAL);

  const area = chartLayout();
  drawCrosshair(area, area.profile); // Behind the plot, to keep its labels clear
  if (!state.probePinned) drawCrosshair(area, area.noise);
  drawFlightProfile(area);
  drawNoiseGraph(area);
  if (state.probePinned) drawCrosshair(area, area.noise); // In front, or the hatching breaks up the heavier line
  drawProbeDots(area);
  drawPinBadge(area);
}

// ---------------------------------------------------------------------------
// Flight profile
// ---------------------------------------------------------------------------

function drawFlightProfile(area) {
  const baseline = baselineAircraft();
  const levelFt = groupedNumber(proposedTopOfDescent().curr);
  const descent = area.compact ? "descent from" : `${levelFt} ft top of descent at`;

  chartTitle(state.runway === "27"
    ? "Flight profile (ft AMSL): RWY 27, approach from the east"
    : "Flight profile (ft AMSL): RWY 09, approach from the west", area.profileHead);
  drawLegend([
    { label: `${baseline === "E190" ? "Today: " : ""}${baseline} at 5.5° (${descent} ${currentTopOfDescent().nm} nm)`, color: COLORS.current },
    { label: `New: A320neo at 4.49° (${descent} ${proposedTopOfDescent().nm} nm)`, color: COLORS.proposed }
  ], area, area.profileHead + 32);

  drawAltitudeGrid(area);
  drawSlopes(area);
  drawWaypoints(area);
  if (area.R - area.L > 640) drawSlopeNames(area);
  drawPlaceNames(area);
}

function altitudeLabel(ft, area) {
  return area.compact ? groupedNumber(ft) : feet(ft);
}

function drawAltitudeGrid(area) {
  const { L, R, profile } = area;
  textSize(11);
  textAlign(RIGHT, CENTER);
  for (let alt = 0; alt <= 3000; alt += 500) {
    const y = altitudeToY(alt, area);
    stroke(alt === 0 ? COLORS.baseline : COLORS.grid);
    line(L, y, R, y);
    noStroke();
    fill(COLORS.inkMuted);
    text(altitudeLabel(alt, area), L - 8, y);
  }

  // Waypoint guides, under the data
  stroke(COLORS.grid);
  for (const w of waypoints()) {
    const x = distanceToX(w.nm, area);
    line(x, altitudeToY(w.curr, area), x, profile.bottom);
  }
}

// The two paths, with the gap between them shaded
function drawSlopes(area) {
  const pathPoints = key => distanceSamples().map(nm => [distanceToX(nm, area), altitudeToY(getAltitudes(nm)[key], area)]);
  const curr = pathPoints("curr");
  const prop = pathPoints("prop");

  noStroke();
  fill(COLORS.proposedTint);
  drawPolygon([...curr, ...[...prop].reverse()]);

  noFill();
  strokeWeight(2);
  stroke(COLORS.current);
  drawPolyline(curr);
  stroke(COLORS.proposed);
  drawPolyline(prop);
  strokeWeight(1);
}

// Waypoint markers and altitude labels; labels too close to the previous one are dropped
function drawWaypoints(area) {
  const rising = state.runway === "27"; // RWY 27 rises to the right, RWY 09 to the left, and each label sits on its slope's outer side
  const hasRoom = (x, lastX, label) => lastX === null || Math.abs(x - lastX) > textWidth(label) + 4;
  let lastCurrX = null;
  let lastPropX = null;

  textSize(11);
  for (const w of waypoints()) {
    const x = distanceToX(w.nm, area);
    const yc = altitudeToY(w.curr, area);
    const yp = altitudeToY(w.prop, area);
    drawMarker(x, yc, COLORS.current, 8);
    drawMarker(x, yp, COLORS.proposed, 8);
    if (w.nm === 0) continue;

    noStroke();
    fill(COLORS.inkSecondary);

    const currLabel = altitudeLabel(w.curr, area);
    if (hasRoom(x, lastCurrX, currLabel)) {
      textAlign(rising ? RIGHT : LEFT, BOTTOM);
      haloText(currLabel, x + (rising ? 8 : -8), yc - 7);
      lastCurrX = x;
    }

    const propLabel = altitudeLabel(w.prop, area);
    if (w.nm < proposedTopOfDescent().nm && hasRoom(x, lastPropX, propLabel)) {
      textAlign(rising ? LEFT : RIGHT, TOP);
      haloText(propLabel, x + (rising ? -8 : 8), yp + 7);
      lastPropX = x;
    }
  }
}

// Direct labels on the slopes, on the free stretch between two waypoints
function drawSlopeNames(area) {
  const nm = state.runway === "27" ? 4.5 : 2.5;
  const x = distanceToX(nm, area);
  const lean = state.runway === "27" ? 1 : -1; // Which way the slope rises across the screen
  const alts = getAltitudes(nm);
  noStroke();
  fill(COLORS.ink);
  textSize(12);
  textStyle(BOLD);
  textAlign(lean > 0 ? RIGHT : LEFT, BOTTOM);
  text(`${baselineAircraft()} 5.5°`, x - lean * 6, altitudeToY(alts.curr, area) - 8);
  textAlign(lean > 0 ? LEFT : RIGHT, TOP);
  text("A320neo 4.49°", x + lean * 6, altitudeToY(alts.prop, area) + 8);
  textStyle(NORMAL);
}

// Place names under the distance axis
function drawPlaceNames(area) {
  noStroke();
  fill(COLORS.inkSecondary);
  textSize(11);
  textAlign(CENTER, TOP);
  for (const label of area.locations) {
    text(label.text, label.x, area.locationsTop + label.row * 17);
  }
}

// ---------------------------------------------------------------------------
// Noise difference
// ---------------------------------------------------------------------------

function drawNoiseGraph(area) {
  chartTitle(`Noise on the ground: A320neo minus ${baselineAircraft()} (Δ ${currentMetric()})`, area.noiseHead);
  drawLegend(noiseLegendItems(area), area, area.noiseHead + 32);
  drawDbGrid(area);

  // +3 dB reference, drawn under the curves with its label over them
  const referenceY = dbToY(NOTICEABLE_DB, area);
  stroke(COLORS.reference);
  withDash([4, 4], () => line(area.L, referenceY, area.R, referenceY));
  noStroke();

  if (usingAirportTable()) {
    drawAirportCurve(area);
  } else {
    drawModelCurves(area);
    drawSiteMarker(area);
  }

  fill(COLORS.inkSecondary);
  textSize(11);
  const referenceLabel = area.compact ? "+3 dB: double acoustic energy" : "+3 dB: double acoustic energy, the airport's \"noticeable\" level";
  textAlign(state.runway === "27" ? RIGHT : LEFT, BOTTOM);
  haloText(referenceLabel, state.runway === "27" ? area.R - 8 : area.L + 8, referenceY - 3);

  drawDistanceAxis(area);
}

function noiseLegendItems(area) {
  if (usingAirportTable()) {
    return [{ label: area.compact ? "Airport prediction (0.5–5 km only)" : "Airport prediction (0.5–5 km; none published outside this range)", color: COLORS.net }];
  }
  if (!hasAdjustments()) return [{ label: "Height + air", color: COLORS.net }];
  return [
    { label: "Total at slider values", color: COLORS.net },
    { label: "Evidence range", color: COLORS.netRange, band: true },
    { label: "Height + air only", color: COLORS.component, dash: [4, 3] },
    ...(showsAirportTableLine() ? [{ label: "Airport table", color: COLORS.ink, dash: [2, 3] }] : [])
  ];
}

// The airport's table is in SEL for a listener below the path, so it only compares with a model scenario in those terms
function showsAirportTableLine() {
  return hasAdjustments() && currentMetric() === "SEL" && !currentScenario().site && hasAirportTable();
}

// The step widens when the plot is short or the scale is wide, and always hits 0 dB
function drawDbGrid(area) {
  const { L, R, noise, bounds: { minDB, maxDB } } = area;
  const pxPerDB = (noise.bottom - noise.top) / (maxDB - minDB);
  const tickStep = pxPerDB >= 18 ? 1 : (pxPerDB >= 9 ? 2 : 4);
  textSize(11);
  textAlign(RIGHT, CENTER);
  for (let db = minDB; db <= maxDB; db++) {
    if (db % tickStep !== 0) continue;
    const y = dbToY(db, area);
    if (db !== 0) {
      stroke(COLORS.grid);
      line(L, y, R, y);
    }
    noStroke();
    fill(db === 0 ? COLORS.ink : COLORS.inkMuted);
    text(`${db > 0 ? "+" : (db < 0 ? "−" : "")}${Math.abs(db)} dB`, L - 8, y);
  }
}

// Zero line and distance axis, over the fill
function drawDistanceAxis(area) {
  const { L, R, noise } = area;
  stroke(COLORS.baseline);
  line(L, dbToY(0, area), R, dbToY(0, area));
  textSize(11);
  textAlign(CENTER, TOP);
  for (let nm = 0; nm <= 6; nm++) {
    const x = distanceToX(nm, area);
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

// The airport's published table as points on the chart
function airportTablePoints(area) {
  return airportTable().map(([km, otherLouder]) => [distanceToX(km / KM_PER_NM, area), dbToY(-otherLouder, area)]);
}

function drawAirportCurve(area) {
  const points = airportTablePoints(area);
  const first = points[0];
  const last = points[points.length - 1];
  const zeroY = dbToY(0, area);

  // Shaded area between the airport's published curve (0.5–5.0 km) and zero
  noStroke();
  fill(COLORS.netTint);
  drawPolygon([[first[0], zeroY], ...points, [last[0], zeroY]]);

  noFill();
  stroke(COLORS.net);
  strokeWeight(2.5);
  drawPolyline(points);
  strokeWeight(1);

  // Endpoint markers showing the exact 0.5 km and 5.0 km boundaries of the published table
  for (const [x, y] of [first, last]) {
    drawMarker(x, y, COLORS.net, 6);
  }
}

function drawModelCurves(area) {
  if (hasAdjustments()) {
    drawNoThrustZone(area);
    drawEvidenceRange(area);
  } else {
    drawHeightAirFill(area);
  }
  if (showsAirportTableLine()) drawAirportTableLine(area);
  if (hasAdjustments()) drawHeightAirLine(area);
  drawTotalLine(area);
}

// Hatches the distances with no thrust estimate, so the missing term doesn't read as zero
function drawNoThrustZone(area) {
  const { noise } = area;
  const edgeX = distanceToX(thrustEstimateEndNM(), area);
  const farX = distanceToX(CHART_MAX_NM, area);
  const left = Math.min(edgeX, farX);
  const right = Math.max(edgeX, farX);
  const plotH = noise.bottom - noise.top;

  drawingContext.save();
  drawingContext.beginPath();
  drawingContext.rect(left, noise.top, right - left, plotH);
  drawingContext.clip();
  stroke(COLORS.grid);
  strokeWeight(1);
  for (let x = left - plotH; x < right; x += 10) {
    line(x, noise.bottom, x + plotH, noise.top);
  }
  drawingContext.restore();
  stroke(COLORS.baseline);
  line(edgeX, noise.top, edgeX, noise.bottom);
  noStroke();
}

function drawEvidenceRange(area) {
  const samples = evidenceSamples();
  const edge = key => samples.map(nm => [distanceToX(nm, area), dbToY(evidenceRangeAt(nm)[key], area)]);
  noStroke();
  fill(COLORS.netRange);
  drawPolygon([...edge("high"), ...edge("low").reverse()]);
}

// The area between the curve and zero, when showing height + air alone
function drawHeightAirFill(area) {
  const zeroY = dbToY(0, area);
  noStroke();
  fill(COLORS.netTint);
  drawPolygon([
    [distanceToX(MIN_MODEL_NM, area), zeroY],
    ...distanceSamples(MIN_MODEL_NM).map(nm => [distanceToX(nm, area), dbToY(getAcoustics(nm).netDB, area)]),
    [distanceToX(CHART_MAX_NM, area), zeroY]
  ]);
}

// Dotted: the airport's own table for this aircraft
function drawAirportTableLine(area) {
  noFill();
  stroke(COLORS.ink);
  strokeWeight(1.5);
  withDash([2, 3], () => drawPolyline(airportTablePoints(area)));
  strokeWeight(1);
  noStroke();
}

// Dashed: height and air alone, when that differs from the total
function drawHeightAirLine(area) {
  noFill();
  stroke(COLORS.component);
  strokeWeight(2);
  withDash([5, 4], () => drawPolyline(distanceSamples(MIN_MODEL_NM).map(nm => {
    const ac = getAcoustics(nm);
    return [distanceToX(nm, area), dbToY(ac.geomDB + ac.atmDB, area)];
  })));
}

// Solid: the total where a thrust estimate exists. Beyond that, a thin dotted line leaves thrust out.
function drawTotalLine(area) {
  noFill();
  stroke(COLORS.net);
  strokeWeight(2.5);
  if (hasAdjustments()) {
    const end = thrustEstimateEndNM();
    traceTotal(MIN_MODEL_NM, end, area);
    strokeWeight(1.5);
    withDash([2, 4], () => traceTotal(end + NM_TOLERANCE, CHART_MAX_NM, area));
  } else {
    traceTotal(MIN_MODEL_NM, CHART_MAX_NM, area);
  }
  strokeWeight(1);
}

function traceTotal(fromNM, toNM, area) {
  const steps = Math.ceil((toNM - fromNM) / 0.05);
  drawPolyline(Array.from({ length: steps + 1 }, (_, i) => {
    const nm = lerp(fromNM, toNM, i / steps);
    return [distanceToX(nm, area), dbToY(getAcoustics(nm).netDB, area)];
  }));
}

// Marks the listener's place on a scenario tied to one site
function drawSiteMarker(area) {
  const scenario = currentScenario();
  if (!scenario.site) return;
  const x = distanceToX(scenario.site.nm, area);
  stroke(COLORS.ink);
  withDash([2, 3], () => line(x, area.noise.top, x, area.noise.bottom));
  noStroke();
  fill(COLORS.ink);
  textSize(11);
  textAlign(LEFT, TOP);
  haloText(scenario.name, x + 5, area.noise.top + 4);
}

// ---------------------------------------------------------------------------
// The line at the selected distance
// ---------------------------------------------------------------------------

function drawCrosshair(area, plot) {
  const x = distanceToX(state.probeNM, area);
  stroke(state.probePinned ? COLORS.ink : COLORS.crosshair);
  strokeWeight(state.probePinned ? 2 : 1);
  line(x, plot.top, x, plot.bottom);
  strokeWeight(1);
  noStroke();
}

function drawProbeDots(area) {
  const nm = state.probeNM;
  const x = distanceToX(nm, area);
  const ac = getAcoustics(nm);
  const airport = probeAirportValues(nm);

  drawProbeDot(x, altitudeToY(ac.currAlt, area), COLORS.current);
  drawProbeDot(x, altitudeToY(ac.propAlt, area), COLORS.proposed);
  if (airport ? airport.predicted : !insideFirstAssessmentPoint(nm)) {
    drawProbeDot(x, dbToY(airport ? airport.db : ac.netDB, area), COLORS.net);
  }
}

function drawProbeDot(x, y, color) {
  stroke(color);
  strokeWeight(2.5);
  fill(255);
  circle(x, y, 10);
  strokeWeight(1);
  noStroke();
}

// A pin and "Pinned" on a pill on the line, at whichever end of the plot is further from the flight paths and their labels
function drawPinBadge(area) {
  if (!state.probePinned) return;
  const label = "Pinned";
  const pillH = 20;
  const iconW = 7;
  const padLeft = 7;
  const iconGap = 4;
  textSize(11);
  textStyle(BOLD);
  const pillW = padLeft + iconW + iconGap + textWidth(label) + 8;
  const left = constrain(distanceToX(state.probeNM, area) - pillW / 2, area.L, area.R - pillW);
  const alts = getAltitudes(state.probeNM);
  const pathY = altitudeToY(Math.max(alts.curr, alts.prop), area);
  const pathNearTop = pathY < (area.profile.top + area.profile.bottom) / 2;
  const top = pathNearTop ? area.profile.bottom - pillH - 4 : area.profile.top;
  const middle = top + pillH / 2;

  noStroke();
  fill(COLORS.ink);
  rect(left, top, pillW, pillH, pillH / 2);

  fill(255);
  const iconX = left + padLeft + iconW / 2;
  circle(iconX, middle - 2, iconW);
  triangle(iconX - 3, middle, iconX + 3, middle, iconX, middle + 6);
  fill(COLORS.ink);
  circle(iconX, middle - 2, 2.5);

  fill(255);
  textAlign(LEFT, CENTER);
  text(label, left + padLeft + iconW + iconGap, middle);
  textStyle(NORMAL);
}

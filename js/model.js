/**
 * The viewer's current choices and the acoustic model that follows from them.
 * Distances are nautical miles from the runway threshold. Deltas are A320neo minus the other type, in dB.
 */

const CHART_MAX_NM = 6.5;
const NM_TOLERANCE = 1e-6; // For comparing distances that have been through a km conversion

const state = {
  scenarioIndex: 1,  // EASA: E190, today's most common aircraft, in LAmax
  runway: "27",
  metric: "LAmax",   // "LAmax" (20 log), the metric this model is mainly for, or "SEL" (10 log). The airport's tables are SEL only.
  sourceDelta: 0,    // The aircraft slider
  thrustDelta: 0,    // The thrust slider
  probeNM: 2.0,      // The distance the line on the charts is at
  probePinned: false // Clicking the charts holds the line in place, so the pointer can leave without moving it
};

function currentScenario() {
  return SCENARIOS[state.scenarioIndex];
}

// The aircraft on the 5.5° approach
function baselineAircraft() {
  return currentScenario().baseline;
}

function usingAirportTable() {
  return currentScenario().usesAirportTable === true;
}

function currentMetric() {
  return usingAirportTable() ? "SEL" : state.metric;
}

function waypoints() {
  return WAYPOINTS_BY_RUNWAY[state.runway];
}

// With both sliders at 0 the model shows height and air alone
function hasAdjustments() {
  return state.sourceDelta !== 0 || state.thrustDelta !== 0;
}

// Whether the sliders differ from the current model scenario's own values
function slidersChanged() {
  const scenario = currentScenario();
  return state.sourceDelta !== scenario.sourceDelta || state.thrustDelta !== scenario.thrustDelta;
}

// ---------------------------------------------------------------------------
// Flight paths
// ---------------------------------------------------------------------------

// Altitudes at any distance, level beyond the proposed top of descent
function getAltitudes(nm) {
  nm = constrain(nm, 0, CHART_MAX_NM);
  const points = waypoints();
  for (let i = 0; i < points.length - 1; i++) {
    const from = points[i];
    const to = points[i + 1];
    if (nm >= from.nm && nm <= to.nm) {
      const t = (nm - from.nm) / (to.nm - from.nm);
      return { curr: lerp(from.curr, to.curr, t), prop: lerp(from.prop, to.prop, t) };
    }
  }
  const level = points[points.length - 1];
  return { curr: level.curr, prop: level.prop };
}

function currentTopOfDescent() {
  const points = waypoints();
  return points[points.length - 2];
}

function proposedTopOfDescent() {
  const points = waypoints();
  return points[points.length - 1];
}

function insideFirstAssessmentPoint(nm) {
  return nm < MIN_MODEL_NM - NM_TOLERANCE;
}

// ---------------------------------------------------------------------------
// Air absorption
// ---------------------------------------------------------------------------

const UNATTENUATED_A_BANDS = ANP_APPROACH_CLASS_205.map(
  (spl, i) => spl + DOC29_ALPHA_DB_PER_100M[i] * 3.05 + IEC_A_WEIGHTING[i]
);
const UNATTENUATED_A_TOTAL = 10 * Math.log10(
  UNATTENUATED_A_BANDS.reduce((sum, level) => sum + 10 ** (level / 10), 0)
);

function airLossDB(heightFt) {
  const d100m = (Math.max(heightFt, 1) * M_PER_FT) / 100;
  let energy = 0;
  for (let i = 0; i < UNATTENUATED_A_BANDS.length; i++) {
    energy += 10 ** ((UNATTENUATED_A_BANDS[i] - DOC29_ALPHA_DB_PER_100M[i] * d100m) / 10);
  }
  return UNATTENUATED_A_TOTAL - 10 * Math.log10(energy);
}

// ---------------------------------------------------------------------------
// Thrust and evidence
// ---------------------------------------------------------------------------

function thrustEstimateEndNM() {
  return Math.min(THRUST_ESTIMATE_END_NM, currentTopOfDescent().nm);
}

function hasThrustEstimate(nm) {
  return nm <= thrustEstimateEndNM() + 1e-9;
}

// The estimated thrust difference, or 0 where no estimate exists (drawn hatched, not as a finding)
function thrustDeltaAt(nm, thrustDelta) {
  return hasThrustEstimate(nm) ? thrustDelta : 0;
}

// The evidence ranges for the current scenario. Scenarios built through the E190 carry its ranges across, shifted by the measured gap.
function activeEvidence() {
  const scenario = currentScenario();
  if (!scenario.e190Gap) {
    return { source: SOURCE_RANGES[scenario.baseline], thrust: THRUST_RANGES[scenario.baseline] };
  }
  const baseRange = SOURCE_RANGES.E190.range;
  const gap = scenario.e190Gap();
  const range = baseRange.map(value => value + gap);
  return {
    source: {
      range,
      text: `E190 range ${signed(baseRange[0], 1)} to ${signed(baseRange[1], 1)}, ${signed(gap, 1)} measured ${scenario.gapPlace}: ${signed(range[0], 1)} to ${signed(range[1], 1)}`
    },
    thrust: THRUST_RANGES.E190
  };
}

// Thrust evidence bounds by flight phase: full 5.5° vs 4.49° band while both descend (even where unestimated);
// −2 to 0 dB where the 5.5° type is still level (no 5.5° relief); ±0.45 dB, a judgement with no source, where both are level beyond the 4.49° TOD.
function thrustRangeAt(nm, thrust) {
  if (nm <= currentTopOfDescent().nm) return thrust;
  if (nm < proposedTopOfDescent().nm) return [Math.min(thrust[0], LEVEL_VS_DESCENDING_DB), 0];
  const levelSpread = Math.abs(thrust[0]);
  return [-levelSpread, levelSpread];
}

// Height + air plus the extremes of the aircraft and thrust evidence. Not a confidence interval.
function evidenceRangeAt(nm) {
  const ac = getAcoustics(nm);
  const heightAir = ac.geomDB + ac.atmDB;
  const evidence = activeEvidence();
  const source = evidence.source.range;
  const thrust = thrustRangeAt(nm, evidence.thrust.range);
  return {
    low: heightAir + source[0] + thrust[0],
    high: heightAir + source[1] + thrust[1]
  };
}

// ---------------------------------------------------------------------------
// Acoustics
// ---------------------------------------------------------------------------

// The acoustic components at a distance, at the current slider values
function getAcoustics(nm) {
  const alts = getAltitudes(nm);
  const lateralFt = (currentScenario().site?.lateralM ?? 0) / M_PER_FT;
  const currHeight = alts.curr - RUNWAY_ELEVATION_FT;
  const propHeight = alts.prop - RUNWAY_ELEVATION_FT;
  const currDistance = Math.hypot(currHeight, lateralFt);
  const propDistance = Math.hypot(propHeight, lateralFt);

  // 20 log10 for peak level (LAmax), 10 log10 for Sound Exposure Level (SEL)
  const coefficient = currentMetric() === "LAmax" ? 20 : 10;
  const geomDB = coefficient * Math.log10(currDistance / propDistance);
  const atmDB = airLossDB(currDistance) - airLossDB(propDistance);
  const sourceDB = state.sourceDelta;
  const thrustDB = thrustDeltaAt(nm, state.thrustDelta);

  return {
    currAlt: alts.curr,
    propAlt: alts.prop,
    deltaFt: currHeight - propHeight,
    geomDB,
    atmDB,
    sourceDB,
    thrustDB,
    netDB: geomDB + atmDB + sourceDB + thrustDB
  };
}

// ---------------------------------------------------------------------------
// The airport's tables
// ---------------------------------------------------------------------------

// The airport publishes no arrival table for some types, such as the Dash 8-Q400
function hasAirportTable() {
  return Boolean(LCY_ARRIVALS[state.runway][baselineAircraft()]);
}

// [km, other type minus A320neo] for the type being compared
function airportTable() {
  return ARRIVAL_KM.map((km, i) => [km, LCY_ARRIVALS[state.runway][baselineAircraft()][i]]);
}

// The airport's predicted A320neo minus other type difference at nm, or null outside its 0.5–5 km table
function airportPrediction(nm) {
  const rawKm = nm * KM_PER_NM;
  const firstKm = ARRIVAL_KM[0];
  const lastKm = ARRIVAL_KM[ARRIVAL_KM.length - 1];
  if (rawKm < firstKm - NM_TOLERANCE || rawKm > lastKm + NM_TOLERANCE) return null;
  const km = constrain(rawKm, firstKm, lastKm);
  const table = airportTable();
  for (let i = 0; i < table.length - 1; i++) {
    if (km >= table[i][0] && km <= table[i + 1][0]) {
      const t = (km - table[i][0]) / (table[i + 1][0] - table[i][0]);
      return -lerp(table[i][1], table[i + 1][1], t);
    }
  }
  return null;
}

// The airport's figure at nm (predicted: true), or predicted: false outside its 0.5–5 km table; null for model scenarios
function probeAirportValues(nm) {
  if (!usingAirportTable()) return null;
  const predicted = airportPrediction(nm);
  return { predicted: predicted !== null, db: predicted };
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

// Formats with an explicit sign and a true minus, never showing "-0.00" or IEEE-754 .x5 under-rounding
function signed(value, decimals) {
  const factor = 10 ** decimals;
  const rounded = Math.round((Math.abs(value) + 1e-12) * factor) / factor;
  if (rounded === 0) return rounded.toFixed(decimals);
  return (value > 0 ? "+" : "−") + rounded.toFixed(decimals);
}

function groupedNumber(value) {
  return value.toLocaleString("en-GB");
}

function feet(value) {
  return `${groupedNumber(Math.round(value))} ft`;
}

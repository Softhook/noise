/**
 * London City approach noise model: data and calculations only, with no drawing or page access.
 * Loaded by index.html before sketch.js, and by the tests in test/model.test.js.
 * Sources for every value are listed in Documents/README.md.
 */
const NoiseModel = (() => {
  const MAX_NM = 6.5;
  const KM_PER_NM = 1.852;
  const ATMOSPHERE_DB_PER_1000FT = 0.6; // No source document; see README

  // LCY Stage 3 Consultation Document: RWY 27 descends from 3,000 ft (Fig. 9), RWY 09 from 2,000 ft (Fig. 8).
  // Two labels are replaced by the 4.49° slope value: 574 ft at 1 nm in Fig. 9 (547 ft) and 1,692 ft in Fig. 8 (1,656 ft).
  const WAYPOINTS = {
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
      { nm: 3.32, curr: 2000, prop: 1656, label: "Curr TOD", loc: "Rotherhithe Tunnel" },
      { nm: 4.05, curr: 2000, prop: 2000, label: "Prop TOD", loc: "Wapping" }
    ]
  };

  // Consultation Figs. 17 (RWY 27) and 18 (RWY 09): each type at 5.5° minus A320neo at 4.49°, dB(A) SEL.
  // Positive means the other type is louder. These are net figures: altitude, source and thrust are all included.
  const ARRIVAL_KM = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0];
  const ARRIVALS = {
    "27": {
      "E190":    [2.2, 1.7, 1.5, 1.3, 1.2, 1.2, 0.7, 0.3, -0.2, -1.0],
      "E190-E2": [-1.5, -1.5, -1.5, -1.4, -1.4, -1.3, -1.2, -1.3, -1.3, -1.9],
      "E195-E2": [-0.8, -1.4, -1.3, -1.1, -1.0, -0.8, -0.9, -0.9, -0.9, -0.9],
      "A220":    [-0.8, -1.3, -1.5, -1.7, -1.8, -1.8, -2.3, -2.7, -3.2, -4.0]
    },
    "09": {
      "E190":    [2.2, 1.7, 1.5, 1.3, 1.3, 1.2, 0.7, 0.3, -0.2, -0.9],
      "E190-E2": [-1.5, -1.5, -1.5, -1.4, -1.3, -1.2, -1.3, -1.3, -1.3, -1.8],
      "E195-E2": [-0.8, -1.4, -1.3, -1.1, -0.9, -0.8, -0.9, -0.9, -0.9, -0.9],
      "A220":    [-0.8, -1.3, -1.5, -1.7, -1.7, -1.8, -2.3, -2.7, -3.2, -3.9]
    }
  };
  const AIRCRAFT = Object.keys(ARRIVALS["27"]);

  // Consultation Fig. 3: annual flights in the forecast without the change, both runways together
  const FLIGHTS_WITHOUT_CHANGE = {
    "E190":    { 2027: 36600, 2038: 3900 },
    "E190-E2": { 2027: 1400,  2038: 3900 },
    "E195-E2": { 2027: 1600,  2038: 67000 },
    "A220":    { 2027: 7000,  2038: 20100 }
  };

  // A320neo minus the other type, in dB. Different metrics and conditions, so a plausible range and not a confidence interval.
  const SOURCE_RANGES = {
    "E190":    { range: [-2.0, 1.1], text: "E190: −2 measured to +1.1 certificates" },
    "E190-E2": { range: [0.6, 1.5],  text: "E190-E2: +0.6 to +1.5 certificates" },
    "E195-E2": { range: [0.3, 1.2],  text: "E195-E2: +0.3 to +1.2 certificates" },
    "A220":    { range: [2.5, 2.5],  text: "A220: +2.5 measured, 19 arrivals each" }
  };
  const THRUST_RANGE = [0.0, 2.5]; // About 0 (no clear effect at Heathrow) to about 2.5 (NASA turbojet study)

  // Thrust is proportional to the sine of the descent angle, so level flight against a 4.49° descent is
  // sin 4.49° / (sin 5.5° − sin 4.49°) times the difference between the two descents.
  const radians = degrees => (degrees * Math.PI) / 180;
  const LEVEL_THRUST_RATIO = Math.sin(radians(4.49)) / (Math.sin(radians(5.5)) - Math.sin(radians(4.49)));
  // Consultation Fig. 22: E190 at 4,000 ft is 73 dB level and 71 dB descending
  const LEVEL_VS_DESCENT_CAP_DB = 2.0;
  // Noise doesn't change at a single point on the ground when thrust changes; half the length of each transition
  const THRUST_TRANSITION_NM = 0.15;

  const lerp = (a, b, t) => a + (b - a) * t;
  const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

  // Linear interpolation through [x, y] points in ascending x; holds the end values outside them
  function interpolate(points, x) {
    if (x <= points[0][0]) return points[0][1];
    for (let i = 0; i < points.length - 1; i++) {
      if (x <= points[i + 1][0]) {
        const t = (x - points[i][0]) / (points[i + 1][0] - points[i][0]);
        return lerp(points[i][1], points[i + 1][1], t);
      }
    }
    return points[points.length - 1][1];
  }

  function altitudes(runway, nm) {
    const points = WAYPOINTS[runway];
    const x = clamp(nm, 0, MAX_NM);
    return {
      curr: interpolate(points.map(w => [w.nm, w.curr]), x),
      prop: interpolate(points.map(w => [w.nm, w.prop]), x)
    };
  }

  // Same-aircraft effect of altitude and air. metric: "LAmax" (20 log) or "SEL" (10 log).
  function altitudeAndAirDB(runway, nm, metric) {
    const { curr, prop } = altitudes(runway, nm);
    const coefficient = metric === "LAmax" ? 20 : 10;
    return coefficient * Math.log10(curr / prop) + ((curr - prop) / 1000) * ATMOSPHERE_DB_PER_1000FT;
  }

  // thrustDB is the extra noise on the 4.49° slope while both aircraft are descending. Between the two
  // descent points the 5.5° aircraft is level and uses more thrust, so the sign reverses. Beyond both, it is zero.
  function thrustTermDB(runway, nm, thrustDB) {
    const points = WAYPOINTS[runway];
    const currentDescent = points[points.length - 2].nm;
    const proposedDescent = points[points.length - 1].nm;
    const levelSegment = thrustDB <= 0
      ? 0
      : -Math.min(thrustDB * LEVEL_THRUST_RATIO, LEVEL_VS_DESCENT_CAP_DB);
    return interpolate([
      [currentDescent - THRUST_TRANSITION_NM, thrustDB],
      [currentDescent + THRUST_TRANSITION_NM, levelSegment],
      [proposedDescent - THRUST_TRANSITION_NM, levelSegment],
      [proposedDescent + THRUST_TRANSITION_NM, 0]
    ], nm);
  }

  function acoustics(runway, nm, { metric, sourceDB, thrustDB }) {
    const { curr, prop } = altitudes(runway, nm);
    const geometryDB = altitudeAndAirDB(runway, nm, metric);
    const thrustTerm = thrustTermDB(runway, nm, thrustDB);
    return {
      currAlt: curr,
      propAlt: prop,
      deltaFt: curr - prop,
      geometryDB,
      sourceDB,
      thrustDB: thrustTerm,
      netDB: geometryDB + sourceDB + thrustTerm
    };
  }

  // Lowest and highest net difference across a source range and a thrust range
  function evidenceRange(runway, nm, { metric, sourceRange, thrustRange }) {
    const geometryDB = altitudeAndAirDB(runway, nm, metric);
    const thrustTerms = thrustRange.map(thrustDB => thrustTermDB(runway, nm, thrustDB));
    return {
      low: geometryDB + sourceRange[0] + Math.min(...thrustTerms),
      high: geometryDB + sourceRange[1] + Math.max(...thrustTerms)
    };
  }

  // The airport's A320neo minus other-type figure at nm, or null outside its 0.5–5 km table
  function airportDifference(runway, aircraft, nm) {
    const km = nm * KM_PER_NM;
    if (km < ARRIVAL_KM[0] || km > ARRIVAL_KM[ARRIVAL_KM.length - 1]) return null;
    return -interpolate(ARRIVAL_KM.map((tableKm, i) => [tableKm, ARRIVALS[runway][aircraft][i]]), km);
  }

  // The constant offset that best fits an airport column once altitude and air are removed (SEL)
  function fittedSourceDB(runway, aircraft) {
    const offsets = ARRIVAL_KM.map((km, i) =>
      -ARRIVALS[runway][aircraft][i] - altitudeAndAirDB(runway, km / KM_PER_NM, "SEL")
    );
    return offsets.reduce((sum, offset) => sum + offset, 0) / offsets.length;
  }

  return {
    MAX_NM,
    KM_PER_NM,
    AIRCRAFT,
    ARRIVAL_KM,
    ARRIVALS,
    WAYPOINTS,
    FLIGHTS_WITHOUT_CHANGE,
    SOURCE_RANGES,
    THRUST_RANGE,
    altitudes,
    altitudeAndAirDB,
    thrustTermDB,
    acoustics,
    evidenceRange,
    airportDifference,
    fittedSourceDB
  };
})();

if (typeof module !== "undefined") module.exports = NoiseModel;

/**
 * London City approach noise model
 * Compares today's most common aircraft, the E190 on the 5.5° approach, with the A320neo,
 * new to the airport, on the proposed 4.49° approach (0 to 6.5 nm from the threshold).
 * The controls are in index.html; this file holds the data, the model and the charts.
 */
// LCY Stage 3 Consultation Document: RWY 27 descends from 3,000 ft AMSL (Fig. 9), RWY 09 from 2,000 ft AMSL (Fig. 8).
// Runway elevation is 20 ft AMSL (Consultation p.11); threshold crossing heights are 35 ft (5.5°) and 50 ft (4.49°)
// above threshold (Stage 2 pp.50, 61), giving 55 ft and 70 ft AMSL at 0.0 nm.
// Two chart labels are replaced by the 4.49° slope value: 574 ft at 1 nm in Fig. 9 (547 ft) and 1,692 ft in Fig. 8 (1,656 ft).
const RUNWAY_ELEVATION_FT = 20;
const WAYPOINTS_BY_RUNWAY = {
  "27": [
    { nm: 0.0,  curr: 55,   prop: 70,   label: "Rwy 27", loc: "Woolwich" },
    { nm: 1.0,  curr: 640,  prop: 547,  label: "1nm",    loc: "Thamesmead" },
    { nm: 2.0,  curr: 1225, prop: 1024, label: "2nm",    loc: "Abbey Wood" },
    { nm: 3.0,  curr: 1810, prop: 1501, label: "3nm",    loc: "Belvedere" },
    { nm: 4.0,  curr: 2395, prop: 1978, label: "4nm",    loc: "Erith Marshes" },
    { nm: 5.03, curr: 3000, prop: 2472, label: "Curr TOD", loc: "Rainham Marshes" },
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

// Directive (EU) 2015/996 (Doc 29), 24 one-third-octave bands from 50 Hz to 10 kHz:
// AIR-1845 attenuation rates in dB/100 m (Appendix D, Table D-1, p.118) and ANP Spectral Class 205
// ("Approach, 2-Engine High-Bypass", unweighted SPL at 305 m / 1,000 ft; Appendix I, Table I-10, p.800).
const DOC29_ALPHA_DB_PER_100M = [
  0.033, 0.033, 0.033, 0.066, 0.066, 0.098, 0.131, 0.131, 0.197, 0.230, 0.295, 0.361,
  0.459, 0.590, 0.754, 0.983, 1.311, 1.705, 2.295, 3.115, 3.607, 5.246, 7.213, 9.836
];
const ANP_APPROACH_CLASS_205 = [
  68.3, 60.7, 64.6, 67.4, 78.4, 74.8, 71.4, 72.4, 72.0, 72.4, 71.6, 72.0,
  71.0, 70.0, 68.9, 67.2, 65.8, 64.4, 63.0, 62.0, 60.6, 54.4, 48.5, 39.0
];
const IEC_A_WEIGHTING = [
  -30.2, -26.2, -22.5, -19.1, -16.1, -13.4, -10.9, -8.6, -6.6, -4.8, -3.2, -1.9,
  -0.8, 0.0, 0.6, 1.0, 1.2, 1.3, 1.2, 1.0, 0.5, -0.1, -1.1, -2.5
];
const UNATTENUATED_A_BANDS = ANP_APPROACH_CLASS_205.map(
  (spl, i) => spl + DOC29_ALPHA_DB_PER_100M[i] * 3.05 + IEC_A_WEIGHTING[i]
);
const UNATTENUATED_A_TOTAL = 10 * Math.log10(
  UNATTENUATED_A_BANDS.reduce((sum, level) => sum + 10 ** (level / 10), 0)
);

function airLossDB(heightFt) {
  const d100m = (Math.max(heightFt, 1) * 0.3048) / 100;
  let energy = 0;
  for (let i = 0; i < UNATTENUATED_A_BANDS.length; i++) {
    energy += 10 ** ((UNATTENUATED_A_BANDS[i] - DOC29_ALPHA_DB_PER_100M[i] * d100m) / 10);
  }
  return UNATTENUATED_A_TOTAL - 10 * Math.log10(energy);
}

const MODEL_NOTE = "LAmax distance: 6 dB per doubling (20 log; LCY Annex C p.41); AEF p.9 gives 10 dB as an unsourced rule of thumb. SEL distance: 10 log lossless line-integral exposure scaling (Directive 2015/996 Appendix E, p.122); a Boeing 747 lateral test implies about 11.6 log before air (NASA TM 83214, Table 1, p.8). Air: 24-band 1/3-octave AIR-1845 attenuation applied to ANP Spectral Class 205 (twin high-bypass approach, Directive 2015/996 Table D-1 p.118 and Table I-10 p.800), the same spectrum for both aircraft. Against CF34-10E approach NPD data (p.747) this is within 0.13 dB per table interval for SEL and overstates the fall by 0.2–0.4 dB per interval for LAmax. The aircraft difference is held constant with distance, a simplification: in the same NPD tables the A320ceo minus E190 gap falls about 1.2–2.5 dB between 200 and 4,000 ft. The shaded range adds the extremes of the aircraft and thrust evidence; it is not a confidence interval. No estimate is plotted inside 0.5 km (0.27 nm), the airport's first assessment point.";

const SOURCE_SLIDER = { min: -4.0, max: 3.0 };
const THRUST_SLIDER = { min: -1.5, max: 3.0 };
// Evidence ranges shown under the sliders; sources are listed in Documents/README.md
// A320neo minus each type: Chapter 4+ certificates, and arrivals measured at Reagan National where available
const SOURCE_RANGES = {
  "E190":    { range: [-2.2, 0.9], text: "vs E190: −2.2 measured to +0.2 certificates (+0.9 with Flap 06 inhibitor records)" },
  "E190-E2": { range: [0.6, 1.3],  text: "vs E190-E2: +0.6 to +1.3 certificates" },
  "E195-E2": { range: [0.3, 1.0],  text: "vs E195-E2: +0.3 to +1.0 certificates" },
  "A220":    { range: [0.1, 2.5],  text: "vs A220: +0.1 to +0.8 certificates, +2.5 measured" }
};
// Estimated thrust difference relative to 3° reference data: ΔL_base(3°→5.5°) − ΔL_A320(3°→4.49°).
// Floor: spoilers cancel all relief on the 5.5° type, leaving −0.45 (the A320's mid relief, 0.34–0.51 dB).
// E190: NPD slopes give +0.7 to +1.2; the airport's AEDT example gives about +2.5 at most (noise scheme p.33).
// Top of each new-generation band: the slope of the engine the airport uses as that type's proxy, scaled by its mass.
// E190-E2 and E195-E2 use the EMB190's CF34-10E; the A220 uses the 737-500's CFM56-3. Neither is that type's real engine.
const THRUST_RANGES = {
  "E190":    { range: [-0.45, 2.5], text: "estimate: −0.45 if spoilers cancel relief, +0.7 to +1.2 NPD, up to +2.5 AEDT example" },
  "E190-E2": { range: [-0.45, 1.4], text: "estimate: −0.45 if spoilers cancel relief, up to +1.4 with the E190's engine slope" },
  "E195-E2": { range: [-0.45, 1.6], text: "estimate: −0.45 if spoilers cancel relief, up to +1.6 with the E190's engine slope" },
  "A220":    { range: [-0.45, 2.7], text: "estimate: −0.45 if spoilers cancel relief, up to +2.7 with its 737-500 proxy's slope" }
};
// The thrust estimate compares aircraft in landing configuration. Doc 29 default profiles put the A320-211 on landing
// flap from about 1,820 ft (3.7 nm on 4.49°) and the EMB190 from 1,500 ft (2.5 nm on 5.5°). Between those the E190 may
// still be at idle, so the difference could be larger. Beyond 3.7 nm, or the 5.5° top of descent if nearer, no estimate is made.
const THRUST_ESTIMATE_END_NM = 3.7;
const LEVEL_VS_DESCENDING_DB = -2;     // E190 level vs descending at 4,000 ft, 73 vs 71 dB SEL (Consultation Fig. 22, p.32)
const NOTICEABLE_DB = 3;               // LCY Consultation 5.4.11: "noticeable differences of 3dB or more"

// LCY Stage 3 Consultation Document (Issue 1.1, Apr 2026), arrivals: Fig. 17 (RWY 27) and Fig. 18 (RWY 09).
// Each type at 5.5° minus the A320neo at 4.49°, dB(A) SEL, at the distances in ARRIVAL_KM. Positive means the other type is louder.
// These are net figures: the lower A320neo altitude is already included. The tables stop at 5 km.
const ARRIVAL_KM = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0];
const LCY_ARRIVALS = {
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
const KM_PER_NM = 1.852;
const MIN_MODEL_NM = ARRIVAL_KM[0] / KM_PER_NM;                     // 0.50 km (0.27 nm), LCY's closest assessment point
const MAX_AIRPORT_NM = ARRIVAL_KM[ARRIVAL_KM.length - 1] / KM_PER_NM; // 5.00 km (2.70 nm), end of LCY's arrival table

// The airport's own comparison of the A320neo with one other type
function airportPreset(aircraft, basis) {
  return {
    name: `Airport: ${aircraft}`,
    baseline: aircraft,
    usesAirportTable: true,
    desc: () => `LCY consultation Figs. 17–18: A320neo at 4.49° vs ${aircraft} at 5.5° (SEL, net, modelled, published 0.5–5 km only).`,
    sources: () => [
      `AEDT 3g model, not measured. ${basis} A320neo: unadjusted AEDT data on LCY profile at 4.49° (Annex C pp.8, 12).`,
      "Published from 0.5 to 5.0 km (0.27–2.70 nm) only (Consultation pp.30–31). For level flight before descent, Consultation Fig. 22 (p.32) gives 80 vs 77–81 dB SEL at 2,000 ft and 75 vs 72–77 dB SEL at 3,000 ft (E190 vs new-generation types). Thrust and weight are estimated internally by AEDT, with no values, flap, gear or weather settings published (Annex C p.7)."
    ]
  };
}

// Shared wording for the two model scenario types. The text ends with a verb, such as "gives".
function modelDesc(aircraft, text, sourceDelta, thrustDelta, note = "") {
  if (!hasAdjustments()) {
    return `Both sliders set to 0 dB: showing height and atmospheric absorption alone on the 4.49° vs 5.5° paths (reset sliders to restore the ${aircraft} scenario values).`;
  }
  const changed = slidersChanged() ? ` Sliders changed: aircraft ${signed(Number(sourceSlider.value), 2)} dB, thrust ${signed(Number(thrustSlider.value), 1)} dB.` : "";
  return `${text} ${signed(sourceDelta, 2)} dB, plus an estimated ${signed(thrustDelta, 1)} dB thrust difference.${note}${changed}`;
}

function thrustSource(thrustDelta, slopeBasis) {
  return `Thrust ${signed(thrustDelta, 1)} dB is an estimate, not a measurement. It assumes constant speed and drag, and Doc 29 approach NPD slopes from the 2015 ANP data, which has no neo, PW1500G or PW1900G tables. ${slopeBasis} Spoiler drag on the 5.5° approach would lower it: if spoilers cancelled all of that aircraft's relief, it would be about −0.45 dB. It is only estimated up to ${THRUST_ESTIMATE_END_NM} nm, or the 5.5° top of descent if nearer, because Doc 29 default profiles put the A320 on landing flap from about 1,820 ft and the E190 from 1,500 ft (Directive pp.198, 221). From 2.5 to 3.7 nm the E190 may still be at idle, so the difference could be larger. Further out, the hatched area has no thrust estimate: the thin line leaves thrust out, and the range keeps the full thrust band. Where the E190 is level and the A320neo still descending, the range extends down by ${Math.abs(LEVEL_VS_DESCENDING_DB)} dB (73 vs 71 dB SEL at 4,000 ft, Consultation Fig. 22, p.32). London City's profiles are custom (Annex C p.8) and may differ from these defaults.`;
}

// Approach certificates (measured at 3.0°) against one other type: A320neo at its lowest listed landing mass,
// 66.3 t (92.0–92.7 across both engines, midpoint 92.35 EPNdB), minus the other type's 3.0° certificate,
// plus the estimated thrust difference between 3°→5.5° (baseline) and 3°→4.49° (A320neo).
function easaPreset(aircraft, certificate, landingMass, sourceDelta, thrustDelta, slopeBasis, note = "") {
  return {
    name: `EASA: ${aircraft}`,
    baseline: aircraft,
    desc: () => modelDesc(aircraft, `Approach certificates (EASA, 3°): A320neo 92.0–92.7 (midpoint 92.35) at 66.3 t vs ${certificate} EPNdB at ${landingMass} gives`, sourceDelta, thrustDelta),
    sourceDelta,
    thrustDelta,
    sources: () => [
      modelSource(),
      `Certificates are in EPNdB at 3° test conditions and certified landing masses, not London City's angles or weights. Using an EPNdB difference as a dB(A) difference is an assumption: EPNdB adds tone corrections and a different frequency weighting, and includes duration. 66.3 t is the lowest listed A320neo mass; no document gives typical London City landing weights. The midpoint is a simple choice for an unknown engine, not a sourced method, and the sources don't say which E190 modifications or A320neo engine would be used there. ${note}`.trim(),
      thrustSource(thrustDelta, slopeBasis)
    ]
  };
}

// Arrivals measured at Reagan National on typical approach angles, in place of the certificate difference
function measuredPreset(aircraft, sourceDelta, thrustDelta, slopeBasis, note, descNote = "") {
  return {
    name: `Measured: ${aircraft}`,
    wide: true,
    baseline: aircraft,
    desc: () => modelDesc(aircraft, `Arrivals measured at Reagan National (AEF report): A320neo minus ${aircraft} in LAmax is`, sourceDelta, thrustDelta, descNote),
    sourceDelta,
    thrustDelta,
    sources: () => [
      modelSource(),
      `${note} Measured at a US airport on typical approach angles, with aircraft weights, engine variants and flight settings not reported, and applied here to SEL as well as LAmax. The monitors are 3.1–7.1 km from the airport, but the figure is applied unchanged from 0.5 km.`,
      thrustSource(thrustDelta, slopeBasis)
    ]
  };
}

const E190_SLOPES = "CF34-10E relief 3°→5.5° is about 1.2–1.55 dB; A320 CFM56-5A and V2527 relief 3°→4.49° is about 0.34–0.51 dB. The airport's AEDT E190 example implies more, up to about +2.5 dB net (noise scheme p.33).";
const FLAT_SLOPES = "No NPD data exists here for this type's engine, so an A320-like slope is assumed, giving about −0.1 to +0.4 dB.";
const E2_SLOPES = `${FLAT_SLOPES} The airport models the E2 family from the EMB190 (Annex C pp.10–11), and the E190's CF34-10E slope would give about +0.9 to +1.6 dB.`;
const A220_SLOPES = `${FLAT_SLOPES} The airport models the A220-100 from the 737-500 (Annex C p.10), whose CFM56-3 slope would give about +2.3 to +2.7 dB, though that is not the A220's engine.`;
const E195_FORECAST = "The most-flown type in the airport's 2038 forecast without the change (Consultation Fig. 3, p.12).";

const PRESETS = [
  airportPreset("E190", "E190: 737-500 data +1.5 dB, fitted at London City noise monitors 1–6 (LCY Annex C pp.9–10). The 3–5 km drop may come from a flap step in that data (1,000 ft in the Doc 29 default profile, Directive p.189), but Annex C's profiles are custom (p.8), so this is an inference."),
  easaPreset("E190", "E190 92.5", "43 t", -0.15, 0.9, E190_SLOPES, "E190 92.5: the airport's example (noise scheme p.33); 92.4 records are Chapter 3 only. The 91.8 records need a Flap 06 inhibitor and are left out of the default, but no source here says which flap setting London City's E190s use: they would give +0.55 dB. Reagan National arrivals measured about −2 dB LAmax (AEF Table 5, p.8)."),
  measuredPreset("E190", -2.0, 0.9, E190_SLOPES, "A320neo minus E190: −2.2, −2.0 and −1.8 dB LAmax at monitors 6, 8 and 17, from 545/180, 959/309 and 26/8 arrivals over 6 months in 2024–25 (AEF Table 5, p.8)."),
  airportPreset("E190-E2", "E190-E2: EMB190 data −0.9 dB (LCY Annex C p.10)."),
  easaPreset("E190-E2", "E190-E2 91.4", "49.05 t", 0.95, 0.1, E2_SLOPES),
  airportPreset("E195-E2", `E195-E2: based on the E190-E2 with an allowance for its larger size (LCY Annex C p.11). ${E195_FORECAST}`),
  easaPreset("E195-E2", "E195-E2 91.7", "54.0 t", 0.65, 0.2, E2_SLOPES, E195_FORECAST),
  airportPreset("A220", "A220-100: 737-500 data −1.5 dB (LCY Annex C p.10). Its table differs from the E190's by exactly 3.0 dB because both use that 737-500 data."),
  easaPreset("A220", "A220-100 91.9", "54.7 t", 0.45, 0.2, A220_SLOPES, "Reagan National arrivals measured +2.5 dB LAmax (AEF Table 6, p.9). The sources disagree on the E190–A220 gap: about 4.7 dB measured at one monitor, 3.0 dB in the airport's tables, 0.6 dB on certificates."),
  measuredPreset("A220", 2.5, 0.2, A220_SLOPES, "A320neo minus A220: 62.0 vs 59.5 dB LAmax at monitor 6, 19 arrivals each in January 2022, which AEF calls a snapshot (Table 6, p.9). The same monitor gives the E190's −2.2 dB, and its A320neo level is similar in both periods (62.0 and 62.8 dB). AEF notes that A220s at London City may be quieter because of their lower take-off weight (p.9).", " Small sample: 19 arrivals each in one month.")
];

const FONT_STACK = 'system-ui, -apple-system, "Segoe UI", sans-serif';
const ALTITUDE_SCALE_FT = 3400; // Headroom above the 3,000 ft level segment
const DEFAULT_MIN_DB = -4;
const DEFAULT_MAX_DB = 6;
const SAMPLE_STEPS = 130; // Sample intervals per curve

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

let activePreset = 1;    // EASA: E190, today's most common aircraft, in LAmax
let baselineAircraft = "E190"; // The aircraft on the 5.5° approach
let sourceSlider, thrustSlider;
const adjustedSource = {}; // Aircraft Δ the viewer has set, by scenario
const adjustedThrust = {}; // Thrust Δ the viewer has set, by scenario
let metricMode = "LAmax"; // "LAmax" (20 log), the metric this model is mainly for, or "SEL" (10 log). The airport's tables are SEL only.
let probeNM = 2.0;        // Default highlight at 2.0 nm
let activeRunway = "27";
let announceTimer = null;

function distanceToX(nm, left, right) {
  const fraction = nm / 6.5;
  return activeRunway === "27"
    ? lerp(left, right, fraction)
    : lerp(right, left, fraction);
}

function waypoints() {
  return WAYPOINTS_BY_RUNWAY[activeRunway];
}

function listenerNote() {
  const turn = activeRunway === "09" ? " Beyond about 4 nm RWY 09 arrivals are turning, so the straight line is a simplification." : "";
  return `Listener directly below the path, flat ground. Place names are approximate.${turn}`;
}

function modelSource() {
  const correction = activeRunway === "27" ? "its 1 nm label of 574 ft corrected to 547 ft" : "its 1,692 ft label replaced by slope value 1,656 ft";
  return `Altitudes (ft AMSL): LCY Consultation ${altitudeFigure()} (${correction}). Runway elevation is ${RUNWAY_ELEVATION_FT} ft AMSL (Consultation p.11) and threshold crossing heights are 35 ft on 5.5° and 50 ft on 4.49° above threshold (Stage 2 pp.50, 61), giving 55 and 70 ft AMSL; acoustic distances use height above the ${RUNWAY_ELEVATION_FT} ft runway plane. ${MODEL_NOTE} ${listenerNote()}`;
}

// The sliders at 0 show height and air alone
function customSources() {
  return [
    modelSource(),
    "With both sliders at 0, this is height and air alone. If other types flew 4.49°, the airport estimates under 2 dB from height (LCY Annex C p.41); the Stage 4 draft rule limits it to authorised A320neo operators."
  ];
}

function altitudeFigure() {
  return activeRunway === "27" ? "Fig. 9, p.23" : "Fig. 8, p.22";
}

function usingAirportTable() {
  return PRESETS[activePreset].usesAirportTable === true;
}

// [km, other type minus A320neo] for the type being compared
function airportTable() {
  return ARRIVAL_KM.map((km, i) => [km, LCY_ARRIVALS[activeRunway][baselineAircraft][i]]);
}

// The airport's predicted A320neo minus other type difference at nm, or null outside its 0.5–5 km table
function airportPrediction(nm) {
  const rawKm = nm * KM_PER_NM;
  const firstKm = ARRIVAL_KM[0];
  const lastKm = ARRIVAL_KM[ARRIVAL_KM.length - 1];
  if (rawKm < firstKm - 1e-6 || rawKm > lastKm + 1e-6) return null;
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

// Interpolate altitudes at any distance x (in nm)
function getAltitudes(nm) {
  nm = constrain(nm, 0, 6.5);
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

function thrustEstimateEndNM() {
  return Math.min(THRUST_ESTIMATE_END_NM, waypoints()[waypoints().length - 2].nm);
}

function hasThrustEstimate(nm) {
  return nm <= thrustEstimateEndNM() + 1e-9;
}

// The estimated thrust difference, or 0 where no estimate exists (drawn hatched, not as a finding)
function thrustDeltaAt(nm, thrustVal) {
  return hasThrustEstimate(nm) ? thrustVal : 0;
}

// Height + air plus the extremes of the aircraft and thrust evidence. Not a confidence interval.
// The thrust band stays at full width everywhere, because a missing estimate isn't a known zero.
function evidenceRangeAt(nm) {
  const ac = getAcoustics(nm);
  const heightAir = ac.geomDB + ac.atmDB;
  const source = SOURCE_RANGES[baselineAircraft].range;
  const thrust = THRUST_RANGES[baselineAircraft].range;
  const points = waypoints();
  const levelVsDescending = nm > points[points.length - 2].nm && nm < points[points.length - 1].nm;
  return {
    low: heightAir + source[0] + (levelVsDescending ? Math.min(thrust[0], LEVEL_VS_DESCENDING_DB) : thrust[0]),
    high: heightAir + source[1] + thrust[1]
  };
}

// Compute acoustic components at distance nm
function getAcoustics(nm) {
  const alts = getAltitudes(nm);
  const currHeight = alts.curr - RUNWAY_ELEVATION_FT;
  const propHeight = alts.prop - RUNWAY_ELEVATION_FT;
  const ratio = currHeight / propHeight;

  // 20*log10 for peak SPL (LAmax), 10*log10 for Sound Exposure Level (SEL)
  const coeff = (metricMode === "LAmax") ? 20.0 : 10.0;
  const geomDB = coeff * Math.log10(ratio);

  // Spectral atmospheric absorption from Directive 2015/996 (Doc 29) Table D-1 + Class 205
  const deltaFt = currHeight - propHeight;
  const atmDB = airLossDB(currHeight) - airLossDB(propHeight);

  const sDelta = Number(sourceSlider.value);
  const tDelta = thrustDeltaAt(nm, Number(thrustSlider.value));

  const netDB = geomDB + atmDB + sDelta + tDelta;
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
      if (slider === sourceSlider) adjustedSource[activePreset] = Number(slider.value);
      if (slider === thrustSlider) adjustedThrust[activePreset] = Number(slider.value);
      refresh();
    });
  }

  byId("reset-sliders").addEventListener("click", () => {
    delete adjustedSource[activePreset];
    delete adjustedThrust[activePreset];
    sourceSlider.value = PRESETS[activePreset].sourceDelta;
    thrustSlider.value = PRESETS[activePreset].thrustDelta;
    refresh();
  });

  PRESETS.forEach((preset, i) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = preset.name;
    button.classList.toggle("is-wide", preset.wide === true);
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
  baselineAircraft = PRESETS[idx].baseline || "E190";
  // The airport's single net figure ignores the sliders, so they keep their values for the next scenario
  if (!PRESETS[idx].usesAirportTable) {
    sourceSlider.value = adjustedSource[idx] ?? PRESETS[idx].sourceDelta;
    thrustSlider.value = adjustedThrust[idx] ?? PRESETS[idx].thrustDelta;
  }
  refresh();
}

// Whether the sliders differ from the current model scenario's own values
function slidersChanged() {
  const preset = PRESETS[activePreset];
  return Number(sourceSlider.value) !== preset.sourceDelta || Number(thrustSlider.value) !== preset.thrustDelta;
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
  const preset = PRESETS[activePreset];

  [...byId("scenarios").children].forEach((button, i) => setPressed(button, i === activePreset));
  document.querySelectorAll("[data-runway]").forEach(button => {
    setPressed(button, button.dataset.runway === activeRunway);
  });
  document.querySelectorAll("[data-metric]").forEach(button => {
    setPressed(button, button.dataset.metric === currentMetric());
    button.disabled = airport;
  });

  byId("scenario-desc").textContent = preset.desc();
  byId("reset-sliders").hidden = airport || !slidersChanged();
  byId("metric-hint").textContent = airport
    ? "The airport's comparison tables give SEL only."
    : (metricMode === "LAmax" ? "Loudest moment of the flyover (20 log)." : "Total sound energy of the flyover (10 log).");

  // The airport's single net figure already contains source and thrust
  byId("slider-note").hidden = !airport;
  byId("source-evidence").hidden = airport;
  byId("thrust-evidence").hidden = airport;
  for (const slider of [sourceSlider, thrustSlider]) {
    slider.disabled = airport;
    slider.closest(".field").classList.toggle("is-disabled", airport);
  }
  const sourceValueText = `${signed(Number(sourceSlider.value), 2)} dB`;
  const thrustValueText = `${signed(Number(thrustSlider.value), 1)} dB`;
  byId("source-value").textContent = airport ? "In LCY figure" : sourceValueText;
  byId("thrust-value").textContent = airport ? "In LCY figure" : thrustValueText;
  sourceSlider.setAttribute("aria-valuetext", airport ? "Included in airport figure" : sourceValueText);
  thrustSlider.setAttribute("aria-valuetext", airport ? "Included in airport figure" : thrustValueText);

  byId("subtitle").textContent = baselineAircraft === "E190"
    ? "Today's most common aircraft, the E190 at 5.5°, compared with the A320neo, new to the airport, at the proposed 4.49°"
    : `The ${baselineAircraft} at 5.5° compared with the A320neo, new to the airport, at the proposed 4.49°`;
  placeBand(byId("band-source"), SOURCE_RANGES[baselineAircraft].range, SOURCE_SLIDER);
  byId("source-evidence-text").textContent = SOURCE_RANGES[baselineAircraft].text;
  placeBand(byId("band-thrust"), THRUST_RANGES[baselineAircraft].range, THRUST_SLIDER);
  byId("thrust-evidence-text").textContent = THRUST_RANGES[baselineAircraft].text;
  byId("r-curr-label").textContent = `${baselineAircraft} altitude (5.5° AMSL)`;
  byId("source-label").textContent = `Aircraft Δ: A320neo minus ${baselineAircraft}`;
  byId("thrust-label").textContent = `Thrust Δ: A320neo minus ${baselineAircraft}`;

  byId("sources").replaceChildren(...(airport || hasAdjustments() ? preset.sources() : customSources()).map(line => {
    const paragraph = document.createElement("p");
    paragraph.textContent = line;
    return paragraph;
  }));

  document.body.classList.toggle("is-airport", airport);
}

function currentMetric() {
  return usingAirportTable() ? "SEL" : metricMode;
}

// Formats with an explicit sign and a true minus, never showing "-0.00" or IEEE-754 .x5 under-rounding
function signed(value, decimals) {
  const factor = 10 ** decimals;
  const rounded = Math.round((Math.abs(value) + 1e-12) * factor) / factor;
  if (rounded === 0) return rounded.toFixed(decimals);
  return (value > 0 ? "+" : "−") + rounded.toFixed(decimals);
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
  probeNM = constrain(fraction * 6.5, 0, 6.5);
  redraw();
}

function moveProbeWithKeys(event) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  event.preventDefault();
  const step = event.shiftKey ? 0.5 : 0.05;
  const rightward = event.key === "ArrowRight";
  // RWY 09 is drawn with distance increasing to the left
  const further = activeRunway === "27" ? rightward : !rightward;
  const prev = probeNM;

  // Snap onto the 0.05 nm grid after visiting an exact km boundary, and stop at 0.50 km / 5.00 km when crossed
  let next;
  if (!event.shiftKey) {
    const gridIndex = further
      ? Math.floor((prev + 1e-6) / step) + 1
      : Math.ceil((prev - 1e-6) / step) - 1;
    next = constrain(gridIndex * step, 0, 6.5);
    const stops = usingAirportTable() ? [MIN_MODEL_NM, MAX_AIRPORT_NM] : [MIN_MODEL_NM];
    for (const stop of stops) {
      if ((prev < stop - 1e-6 && next > stop - 1e-6) || (prev > stop + 1e-6 && next < stop + 1e-6)) {
        next = stop;
        break;
      }
    }
  } else {
    next = constrain(prev + (further ? step : -step), 0, 6.5);
  }

  probeNM = next;
  redraw();
  announceProbe();
}

function announceProbe() {
  clearTimeout(announceTimer);
  announceTimer = setTimeout(() => {
    const status = byId("probe-status");
    if (status) {
      const rangeText = byId("r-range").textContent;
      status.textContent = `${byId("r-distance").textContent}: ${byId("r-net-label").textContent} ${byId("r-net").textContent}${rangeText === "—" ? "" : `, evidence range ${rangeText}`}`;
    }
  }, 150);
}

// ---------------------------------------------------------------------------
// Chart layout, all in real canvas pixels
// ---------------------------------------------------------------------------

function noiseBounds() {
  let minDB = DEFAULT_MIN_DB;
  let maxDB = DEFAULT_MAX_DB;
  if (usingAirportTable()) return { minDB, maxDB };

  let curveMin = 0;
  let curveMax = 0;
  for (let i = 0; i <= SAMPLE_STEPS; i++) {
    const nm = lerp(MIN_MODEL_NM, 6.5, i / SAMPLE_STEPS);
    const ac = getAcoustics(nm);
    const geomAtm = ac.geomDB + ac.atmDB;
    const range = hasAdjustments() ? evidenceRangeAt(nm) : { low: ac.netDB, high: ac.netDB };
    curveMin = Math.min(curveMin, ac.netDB, geomAtm, range.low);
    curveMax = Math.max(curveMax, ac.netDB, geomAtm, range.high);
  }
  if (curveMin < minDB + 0.2) minDB = Math.floor((curveMin - 0.3) / 2) * 2;
  if (curveMax > maxDB - 0.2) maxDB = Math.ceil((curveMax + 0.3) / 2) * 2;
  return { minDB, maxDB };
}

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
  const profileH = plots * 0.55;

  const profileTop = head;
  const profileBottom = profileTop + profileH;
  const noiseHead = profileBottom + locationsH + betweenCharts;
  const noiseTop = noiseHead + noiseHeadH;
  const noiseBottom = height - axisH;

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
    if (item.band) {
      noStroke();
      fill(item.color);
      rect(x, rowY - 5, 18, 10);
    } else {
      stroke(item.color);
      strokeWeight(2);
      if (item.dashed) drawingContext.setLineDash(item.dashed === true ? [4, 3] : item.dashed);
      line(x, rowY, x + 18, rowY);
      drawingContext.setLineDash([]);
    }
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
  const { minDB, maxDB } = area.bounds;
  return map(constrain(db, minDB, maxDB), minDB, maxDB, area.noise.bottom, area.noise.top);
}

function traceAltitude(key, area) {
  beginShape();
  for (let i = 0; i <= SAMPLE_STEPS; i++) {
    const nm = (i / SAMPLE_STEPS) * 6.5;
    vertex(distanceToX(nm, area.L, area.R), altitudeToY(getAltitudes(nm)[key], area));
  }
  endShape();
}

function drawFlightProfile(area) {
  const { L, R, profile } = area;
  const points = waypoints();
  const propTOD = points[points.length - 1];
  const currTOD = points[points.length - 2];
  const levelFt = propTOD.curr.toLocaleString("en-GB");

  chartTitle(activeRunway === "27"
    ? "Flight profile (ft AMSL): RWY 27, approach from the east"
    : "Flight profile (ft AMSL): RWY 09, approach from the west", area.profileHead);
  drawLegend([
    { label: `${baselineAircraft === "E190" ? "Today: " : ""}${baselineAircraft} at 5.5° (${area.compact ? "descent from" : `${levelFt} ft top of descent at`} ${currTOD.nm} nm)`, color: COLORS.current },
    { label: `New: A320neo at 4.49° (${area.compact ? "descent from" : `${levelFt} ft top of descent at`} ${propTOD.nm} nm)`, color: COLORS.proposed }
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
  for (let i = 0; i <= SAMPLE_STEPS; i++) {
    const nm = (i / SAMPLE_STEPS) * 6.5;
    vertex(distanceToX(nm, L, R), altitudeToY(getAltitudes(nm).curr, area));
  }
  for (let i = SAMPLE_STEPS; i >= 0; i--) {
    const nm = (i / SAMPLE_STEPS) * 6.5;
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
    textAlign(lean > 0 ? RIGHT : LEFT, BOTTOM);
    text(`${baselineAircraft} 5.5°`, x - lean * 6, altitudeToY(alts.curr, area) - 8);
    textAlign(lean > 0 ? LEFT : RIGHT, TOP);
    text("A320neo 4.49°", x + lean * 6, altitudeToY(alts.prop, area) + 8);
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
  const { L, R, noise, bounds } = area;
  const { minDB, maxDB } = bounds;
  const airport = usingAirportTable();

  chartTitle(`Noise on the ground: A320neo minus ${baselineAircraft} (Δ ${currentMetric()})`, area.noiseHead);
  drawLegend(airport
    ? [
      { label: area.compact ? "Airport prediction (0.5–5 km only)" : "Airport prediction (0.5–5 km; none published outside this range)", color: COLORS.net }
    ]
    : (hasAdjustments()
      ? [
        { label: "Total at slider values", color: COLORS.net },
        { label: "Evidence range", color: COLORS.netRange, band: true },
        { label: "Height + air only", color: COLORS.component, dashed: true },
        ...(currentMetric() === "SEL" ? [{ label: "Airport table", color: COLORS.ink, dashed: [2, 3] }] : [])
      ]
      : [{ label: "Height + air", color: COLORS.net }]), area, area.noiseHead + 32);

  // dB grid; step expands cleanly when the plot is short or slider bounds widen, always hitting 0 dB
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
  const refLabel = area.compact ? "+3 dB: double acoustic energy" : "+3 dB: double acoustic energy, the airport's \"noticeable\" level";
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

function hasAdjustments() {
  return Number(sourceSlider.value) !== 0 || Number(thrustSlider.value) !== 0;
}

function drawAirportCurve(area) {
  const { L, R } = area;
  const table = airportTable();
  const first = table[0];
  const last = table[table.length - 1];

  // Shaded area between the airport's published curve (0.5–5.0 km) and zero
  noStroke();
  fill(COLORS.netTint);
  beginShape();
  vertex(distanceToX(first[0] / KM_PER_NM, L, R), dbToY(0, area));
  for (const [km, otherLouder] of table) {
    vertex(distanceToX(km / KM_PER_NM, L, R), dbToY(-otherLouder, area));
  }
  vertex(distanceToX(last[0] / KM_PER_NM, L, R), dbToY(0, area));
  endShape(CLOSE);

  // Solid: the airport's published figures (0.5–5.0 km only)
  noFill();
  stroke(COLORS.net);
  strokeWeight(2.5);
  beginShape();
  for (const [km, otherLouder] of table) {
    vertex(distanceToX(km / KM_PER_NM, L, R), dbToY(-otherLouder, area));
  }
  endShape();
  strokeWeight(1);

  // Endpoint markers showing the exact 0.5 km and 5.0 km boundaries of the published table
  for (const [km, otherLouder] of [first, last]) {
    drawMarker(distanceToX(km / KM_PER_NM, L, R), dbToY(-otherLouder, area), COLORS.net, 6);
  }
}

function drawModelCurves(area) {
  const { L, R } = area;

  if (hasAdjustments()) drawNoThrustZone(area);

  // Shaded evidence range, or the area between the curve and zero when showing height + air alone
  noStroke();
  beginShape();
  if (hasAdjustments()) {
    fill(COLORS.netRange);
    for (let i = 0; i <= SAMPLE_STEPS; i++) {
      const nm = lerp(MIN_MODEL_NM, 6.5, i / SAMPLE_STEPS);
      vertex(distanceToX(nm, L, R), dbToY(evidenceRangeAt(nm).high, area));
    }
    for (let i = SAMPLE_STEPS; i >= 0; i--) {
      const nm = lerp(MIN_MODEL_NM, 6.5, i / SAMPLE_STEPS);
      vertex(distanceToX(nm, L, R), dbToY(evidenceRangeAt(nm).low, area));
    }
  } else {
    fill(COLORS.netTint);
    vertex(distanceToX(MIN_MODEL_NM, L, R), dbToY(0, area));
    for (let i = 0; i <= SAMPLE_STEPS; i++) {
      const nm = lerp(MIN_MODEL_NM, 6.5, i / SAMPLE_STEPS);
      vertex(distanceToX(nm, L, R), dbToY(getAcoustics(nm).netDB, area));
    }
    vertex(distanceToX(6.5, L, R), dbToY(0, area));
  }
  endShape(CLOSE);

  // Dotted: the airport's own table for this aircraft, which is in SEL, so only drawn in SEL
  if (hasAdjustments() && currentMetric() === "SEL") {
    noFill();
    stroke(COLORS.ink);
    strokeWeight(1.5);
    drawingContext.setLineDash([2, 3]);
    beginShape();
    for (const [km, otherLouder] of airportTable()) {
      vertex(distanceToX(km / KM_PER_NM, L, R), dbToY(-otherLouder, area));
    }
    endShape();
    drawingContext.setLineDash([]);
    strokeWeight(1);
    noStroke();
  }

  // Dashed: altitude and atmosphere alone, when that differs from the total
  noFill();
  if (hasAdjustments()) {
    stroke(COLORS.component);
    strokeWeight(2);
    drawingContext.setLineDash([5, 4]);
    beginShape();
    for (let i = 0; i <= SAMPLE_STEPS; i++) {
      const nm = lerp(MIN_MODEL_NM, 6.5, i / SAMPLE_STEPS);
      const ac = getAcoustics(nm);
      vertex(distanceToX(nm, L, R), dbToY(ac.geomDB + ac.atmDB, area));
    }
    endShape();
    drawingContext.setLineDash([]);
  }

  // Solid: the total where a thrust estimate exists. Beyond that, a thin dotted line leaves thrust out.
  noFill();
  stroke(COLORS.net);
  strokeWeight(2.5);
  if (hasAdjustments()) {
    const end = thrustEstimateEndNM();
    traceTotal(MIN_MODEL_NM, end, area);
    strokeWeight(1.5);
    drawingContext.setLineDash([2, 4]);
    traceTotal(end + 1e-6, 6.5, area);
    drawingContext.setLineDash([]);
  } else {
    traceTotal(MIN_MODEL_NM, 6.5, area);
  }
  strokeWeight(1);
}

function traceTotal(fromNM, toNM, area) {
  const steps = Math.ceil((toNM - fromNM) / 0.05);
  beginShape();
  for (let i = 0; i <= steps; i++) {
    const nm = lerp(fromNM, toNM, i / steps);
    vertex(distanceToX(nm, area.L, area.R), dbToY(getAcoustics(nm).netDB, area));
  }
  endShape();
}

// Hatches the distances with no thrust estimate, so the missing term doesn't read as zero
function drawNoThrustZone(area) {
  const { noise } = area;
  const edgeX = distanceToX(thrustEstimateEndNM(), area.L, area.R);
  const farX = distanceToX(6.5, area.L, area.R);
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

// The airport's figure at nm (predicted: true), or predicted: false outside its 0.5–5 km table; null for model scenarios
function probeAirportValues(nm) {
  if (!usingAirportTable()) return null;
  const predicted = airportPrediction(nm);
  return { predicted: predicted !== null, db: predicted };
}

function insideFirstAssessmentPoint(nm) {
  return nm < MIN_MODEL_NM - 1e-6;
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
  if (airport ? airport.predicted : !insideFirstAssessmentPoint(probeNM)) {
    drawProbeDot(x, dbToY(airport ? airport.db : ac.netDB, area), COLORS.net);
  }
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
  const tooClose = insideFirstAssessmentPoint(probeNM);

  byId("r-distance").textContent = `${probeNM.toFixed(2)} nm · ${(probeNM * KM_PER_NM).toFixed(2)} km`;
  byId("r-curr").textContent = feet(ac.currAlt);
  byId("r-prop").textContent = feet(ac.propAlt);
  byId("r-drop").textContent = `${signed(-Math.round(ac.deltaFt), 0)} ft`;

  const geomEl = byId("r-geom");
  const sourceEl = byId("r-source");
  const netEl = byId("r-net");
  const geomSum = ac.geomDB + ac.atmDB;
  const sourceSum = ac.sourceDB + ac.thrustDB;

  geomEl.textContent = tooClose ? "—" : `${signed(geomSum, 1)} dB`;
  geomEl.title = tooClose ? "" : `${signed(geomSum, 2)} dB unrounded`;
  const noThrust = !airport && hasAdjustments() && !hasThrustEstimate(probeNM);
  sourceEl.textContent = tooClose ? "—" : `${signed(sourceSum, 1)} dB${noThrust ? " (no thrust)" : ""}`;
  sourceEl.title = tooClose ? "" : `${signed(sourceSum, 2)} dB unrounded`;

  const range = !airport && !tooClose && hasAdjustments() ? evidenceRangeAt(probeNM) : null;
  byId("r-range").textContent = range ? `${signed(range.low, 1)} to ${signed(range.high, 1)} dB` : "—";
  const crossed = range ? [-NOTICEABLE_DB, 0, NOTICEABLE_DB].filter(level => range.low < level && range.high > level) : [];
  const rangeNote = byId("r-range-note");
  rangeNote.textContent = crossed.length
    ? `Range crosses ${crossed.map(level => (level === 0 ? "no change" : `${signed(level, 0)} dB`)).join(", ").replace(/, ([^,]*)$/, " and $1")}`
    : "";
  const tableDB = airportPrediction(probeNM);
  byId("r-table").textContent = tableDB === null ? "Outside 0.5–5 km" : `${signed(tableDB, 1)} dB SEL`;

  const pair = `A320neo minus ${baselineAircraft}`;
  const chip = byId("r-chip");

  if (airport && !airport.predicted) {
    byId("r-net-label").textContent = "Airport prediction (0.5–5 km only)";
    netEl.textContent = "Outside 0.5–5 km table";
    netEl.title = "";
    chip.hidden = true;
    return;
  }

  if (!airport && tooClose) {
    byId("r-net-label").textContent = "Ground noise (< 0.5 km)";
    netEl.textContent = "No estimate";
    netEl.title = "The airport's tables start at 0.5 km, so no estimate is plotted closer to the threshold";
    chip.hidden = true;
    return;
  }

  const db = airport ? airport.db : ac.netDB;
  byId("r-net-label").textContent = airport ? `Airport prediction, ${pair}` : (noThrust ? `${pair}, leaving out thrust` : pair);
  netEl.textContent = `${signed(db, 1)} dB ${currentMetric()}`;
  netEl.title = `${signed(db, 2)} dB ${currentMetric()} unrounded`;

  // The chip describes the selected value, and the note beside it says what the evidence range crosses.
  // Red and green are for values the airport would call noticeable, and need a complete figure.
  chip.hidden = false;
  const louder = db > 0.2, quieter = db < -0.2;
  const noticeable = !noThrust && Math.abs(db) >= NOTICEABLE_DB;
  chip.textContent = louder ? "▲ Louder" : (quieter ? "▼ Quieter" : "≈ No change");
  chip.className = `chip${noticeable && louder ? " is-louder" : ""}${noticeable && quieter ? " is-quieter" : ""}`;
}

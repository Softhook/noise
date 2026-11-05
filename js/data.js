/**
 * Sourced figures for the noise model: flight paths, spectra, evidence ranges and measurements.
 * Nothing here depends on the page. Sources are listed in Documents/README.md.
 */

const KM_PER_NM = 1.852;
const M_PER_FT = 0.3048;

// ---------------------------------------------------------------------------
// Flight paths
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Air absorption
// ---------------------------------------------------------------------------

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
// IEC 61672-1:2013 A-frequency-weighting corrections at nominal 1/3-octave band centers, 50 Hz–10 kHz.
const IEC_A_WEIGHTING = [
  -30.2, -26.2, -22.5, -19.1, -16.1, -13.4, -10.9, -8.6, -6.6, -4.8, -3.2, -1.9,
  -0.8, 0.0, 0.6, 1.0, 1.2, 1.3, 1.2, 1.0, 0.5, -0.1, -1.1, -2.5
];

// ---------------------------------------------------------------------------
// Sliders and evidence ranges
// ---------------------------------------------------------------------------

const SOURCE_SLIDER = { min: -4.0, max: 6.0 };
const THRUST_SLIDER = { min: -1.5, max: 3.0 };
// Evidence ranges shown under the sliders; sources are listed in Documents/README.md
// A320neo minus each type: Chapter 4+ certificates across certified landing masses (66.3–68.4 t), and measured arrivals where available
const SOURCE_RANGES = {
  "E190":    { range: [-2.2, 1.1], text: "vs E190: −2.2 measured, −0.8 to +0.4 EASA certificates (+1.1 with Flap 06 inhibitor)" },
  "E190-E2": { range: [0.6, 1.5],  text: "vs E190-E2: +0.6 to +1.5 EASA certificates (66.3–68.4 t)" },
  "E195-E2": { range: [0.3, 1.2],  text: "vs E195-E2: +0.3 to +1.2 EASA certificates (66.3–68.4 t)" },
  "A220":    { range: [0.1, 2.5],  text: "vs A220: +0.1 to +1.0 EASA certificates (66.3–68.4 t), +2.5 measured" },
  "Dash 8-Q400": { range: [-2.9, 3.15], text: "vs Dash 8-Q400: −2.9 to −0.1 EASA certificates, +3.15 via monitor 6 (includes 5.5° approach)" }
};
// Estimated thrust difference relative to 3° reference data: ΔL_base(3°→5.5°) − ΔL_A320(3°→4.49°).
// Floor: spoilers cancel all relief on the 5.5° type, leaving −0.45 (the A320's mid relief at 1,000 ft, 0.34–0.51 dB).
// E190: NPD slopes give +0.7 to +1.2; the airport's AEDT example gives about +2.5 at most (noise scheme p.33). The default is +0.4, a judgement.
// Top of each new-generation band: the slope of the engine the airport uses as that type's proxy, scaled by its mass.
// E190-E2 and E195-E2 use the EMB190's CF34-10E; the A220 uses the 737-500's CFM56-3. Neither is that type's real engine.
const THRUST_RANGES = {
  "E190":    { range: [-0.45, 2.5], text: "estimate: −0.45 if spoilers cancel relief, +0.4 default (judgement), +0.7 to +1.2 NPD, up to +2.5 AEDT example" },
  "E190-E2": { range: [-0.45, 1.4], text: "estimate: −0.45 if spoilers cancel relief, up to +1.4 with the E190's engine slope" },
  "E195-E2": { range: [-0.45, 1.6], text: "estimate: −0.45 if spoilers cancel relief, up to +1.6 with the E190's engine slope" },
  "A220":    { range: [-0.45, 2.7], text: "estimate: −0.45 if spoilers cancel relief, up to +2.7 with its 737-500 proxy's slope" },
  "Dash 8-Q400": { range: [-0.45, 0.7], text: "estimate: −0.45 if all relief is cancelled, +0.7 with E190's turbofan slope (propeller unloading is in +3.15 above)" }
};
const E190_CERTIFICATE_DELTA = -0.15; // A320neo minus E190: certificate midpoint 92.35 vs 92.5 EPNdB
const E190_MEASURED_DELTA = -2.0;     // A320neo minus E190: Reagan National arrivals (AEF Table 5, p.8)
const E190_THRUST_DELTA = 0.4;        // Judgement, below the +0.7 to +1.2 from NPD slopes; reasons in Documents/README.md
// The thrust estimate compares aircraft in landing configuration. Doc 29 default profiles put the A320-211 on landing
// flap from about 1,820 ft (3.7 nm on 4.49°) and the EMB190 from 1,500 ft (2.5 nm on 5.5°). Between those the E190 may
// still be at idle, so the difference could be larger. Beyond 3.7 nm, or the 5.5° top of descent if nearer, no estimate is made.
const THRUST_ESTIMATE_END_NM = 3.7;
const LEVEL_VS_DESCENDING_DB = -2;     // Level vs descending at 4,000 ft: E190 73 vs 71, new-gen 69–74 vs 68–72 dB SEL, no turboprops (Consultation Fig. 22, p.32)
const NOTICEABLE_DB = 3;               // LCY Consultation 5.4.11: "noticeable differences of 3dB or more"

// ---------------------------------------------------------------------------
// Measurements at London City
// ---------------------------------------------------------------------------

// RWY 27 arrivals measured at London City's NMT6, which they overfly, 2 Sep to 8 Oct 2024 (BAP Thamesmead survey, Table 3, p.8).
const MONITOR_6 = {
  "E190":    { flights: 955, LAmax: 74.8, SEL: 83.8 },
  "E190-E2": { flights: 15,  LAmax: 72.7, SEL: 81.6 },
  "A220":    { flights: 53,  LAmax: 74.3, SEL: 83.7 },
  "Dash 8-Q400": { flights: 78, LAmax: 71.5, SEL: 81.2 }
};
// RWY 27 arrivals measured at the Thamesmead survey site, 2 Sep to 8 Oct 2024 (BAP Thamesmead survey, Table 1, p.6).
// The site is around 4 km from the RWY 27 threshold and around 500 m north of the arrival path (pp.4–5). RWY 09 arrivals don't fly near it.
const THAMESMEAD_GARDEN = {
  km: 4,
  lateralM: 500,
  levels: {
    "E190":     { flights: 1009, LAmax: 63.0, SEL: 72.9 },
    "A220":     { flights: 48,   LAmax: 62.1, SEL: 71.1 },
    "E190-E2":  { flights: 12,   LAmax: 61.3, SEL: 70.5 },
    "Dash 8-Q400": { flights: 85, LAmax: 59.8, SEL: 68.3 }
  }
};

// ---------------------------------------------------------------------------
// The airport's own arrival tables
// ---------------------------------------------------------------------------

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
const MIN_MODEL_NM = ARRIVAL_KM[0] / KM_PER_NM;                     // 0.50 km (0.27 nm), LCY's closest assessment point
const MAX_AIRPORT_NM = ARRIVAL_KM[ARRIVAL_KM.length - 1] / KM_PER_NM; // 5.00 km (2.70 nm), end of LCY's arrival table

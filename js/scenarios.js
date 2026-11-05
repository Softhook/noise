/**
 * The scenarios in the sidebar, and the wording that explains each one.
 * Note text can mark **bold** words and is passed through setCitedText, so citations become links.
 * Each source string is one paragraph, and starts with a bold label.
 */

const SMALL_SAMPLE_FLIGHTS = 20;

// ---------------------------------------------------------------------------
// Wording shared across scenarios
// ---------------------------------------------------------------------------

const MODEL_NOTES = [
  "**Distance.** **LAmax: 6 dB per doubling** (20 log; LCY Annex C p.41); AEF p.9 gives 10 dB as an unsourced rule of thumb. **SEL: 10 log**, lossless line-integral exposure scaling (Directive 2015/996 Appendix E, p.122); a Boeing 747 lateral test implies about 11.6 log before air (NASA TM 83214, Table 1, p.8).",
  "**Air.** 24-band 1/3-octave AIR-1845 attenuation applied to ANP Spectral Class 205 (twin high-bypass approach, Directive 2015/996 Table D-1 p.118 and Table I-10 p.800), the same spectrum for both aircraft. Against CF34-10E approach NPD data (Directive p.747) this is within 0.13 dB per table interval for SEL and overstates the fall by 0.2–0.4 dB per interval for LAmax.",
  "**Aircraft difference.** Held constant with distance, a simplification: in the same NPD tables (Directive 2015/996 pp.747, 753, 793) the A320ceo minus E190 gap falls about 1.4–2.6 dB LAmax and 2.2–4.2 dB SEL between 200 and 4,000 ft, at each aircraft's 3° thrust. Certification is at about 390 ft while Reagan National's monitors are 3.1–7.1 km out, so slower decay of the E190's spectrum with distance could explain part of the gap between certificates (−0.15 dB) and Reagan National (−2.0 dB).",
  "**Evidence range.** The shaded range adds the extremes of the aircraft and thrust evidence; **it is not a confidence interval**.",
  "**Closest point.** No estimate is plotted inside 0.5 km (0.27 nm), the airport's first assessment point."
];

// What every scenario other than the airport's adds to its aircraft difference
const MODELLED_ON_TOP = "Height and air are then modelled, and thrust is estimated.";

// Where each type's approach certificate is listed
const CERTIFICATE_SOURCES = {
  "E190": "EASA ERJ 190 sheet p.46",
  "E190-E2": "EASA ERJ 190 sheet p.190",
  "E195-E2": "EASA ERJ 190 sheet p.194",
  "A220": "EASA A220 sheet p.3",
  "Dash 8-Q400": "EASA DHC-8 sheet p.48 (94.9) and p.50 (93.0 with the 850 rpm approach)"
};

// How each type's thrust estimate was reached
const E190_SLOPES = "CF34-10E relief 3°→5.5° is about 1.2–1.55 dB; A320 CFM56-5A and V2527 relief 3°→4.49° is about 0.34–0.51 dB. Those slopes give **+0.7 to +1.2 dB**, and the airport's AEDT E190 example implies up to about **+2.5 dB** net (noise scheme p.33). **The +0.4 dB default is a judgement**, set lower because half the E190 range is below its table, the slopes ignore spoilers, a same-type A220 comparison shows little relief, and A321neo flight-recorder and 737 steep-approach tests show no clear thrust effect. No E190 has been measured at both angles.";
const FLAT_SLOPES = "No NPD data exists here for this type's engine, so an A320-like slope is **assumed**, giving about **−0.1 to +0.4 dB**.";
const E190_E2_SLOPES = `${FLAT_SLOPES} The airport models the E2 family from the EMB190 (Annex C pp.10–11), and the E190's CF34-10E slope would give about **+0.9 to +1.4 dB**.`;
const E195_E2_SLOPES = `${FLAT_SLOPES} The airport models the E2 family from the EMB190 (Annex C pp.10–11), and the E190's CF34-10E slope would give about **+1.0 to +1.6 dB**.`;
const A220_SLOPES = `${FLAT_SLOPES} The airport models the A220-100 from the 737-500 (Annex C p.10), whose CFM56-3 slope would give about **+2.3 to +2.7 dB**, though that is not the A220's engine.`;
const Q400_SLOPES = "No NPD data exists here for its PW150A: the older Dash 8 PW120 table uses percentage of static thrust and jumps 3.8 dB LAmax at 1,000 ft from 35% to 40%, about 240–250 lbf, which suggests strong sensitivity at low power, though it isn't this aircraft's engine (Directive pp.180, 770). London City's quota scheme notes that 3°→5.5° AEDT scaling from noise certificates does not reflect turboprops on steeper approaches and validates them against 5.5° monitor data instead (noise scheme pp.11–12). Here turbofan slopes are **assumed** for the EASA scenario: an A320-like slope gives about **−0.3 to 0 dB**, and the E190's CF34-10E slope about **+0.7 dB** at most; the −0.45 dB floor is kept if all relief is cancelled.";

const Q400_NOTE = "A turboprop. The air step uses a twin-jet spectrum; Doc 29 turboprop spectra lower the air difference by 0.1–0.3 dB (Directive Table I-10, p.800). **The certificates and the measurements disagree:** certificates put it 0.5–2.4 EPNdB louder than the E190, while London City's survey measured it **3.3 dB LAmax and 2.6 dB SEL quieter at monitor 6**, and 3.2 and 4.6 dB quieter in the Thamesmead garden (Bickerdike Allen, Tables 1 and 3). London City's quota scheme says AEDT scaling from certificates doesn't reflect turboprops on steeper approaches, without saying why (noise scheme pp.11–12). Propeller unloading on 5.5° and EPNdB tone penalties are possible reasons, but no source here tests them. The airport models DH8D arrivals internally from SD330 +2.1 dB (Annex C Table 4, p.10) but publishes no arrival table for it, forecasting about 3,800 Dash 8 movements in 2027 and none in 2038 (Consultation Fig. 3, p.12).";
const E195_FORECAST = "The most-flown type in the airport's 2038 forecast without the change (Consultation Fig. 3, p.12).";

// The certificate difference and thrust estimate used by more than one scenario for a type
const E190_ESTIMATE = { sourceDelta: E190_CERTIFICATE_DELTA, thrustDelta: E190_THRUST_DELTA, slopeBasis: E190_SLOPES };
const E190_E2_ESTIMATE = { sourceDelta: 0.95, thrustDelta: 0.1, slopeBasis: E190_E2_SLOPES };
const A220_ESTIMATE = { sourceDelta: 0.45, thrustDelta: 0.2, slopeBasis: A220_SLOPES };

function aboutThisAircraft(note) {
  return note ? [`**About this aircraft.** ${note}`] : [];
}

function smallSampleNote(aircraft, flights) {
  return flights < SMALL_SAMPLE_FLIGHTS ? ` **Small sample:** ${flights} ${aircraft} arrivals.` : "";
}

function slidersChangedNote() {
  return slidersChanged() ? ` Sliders changed: aircraft ${signed(state.sourceDelta, 2)} dB, thrust ${signed(state.thrustDelta, 1)} dB.` : "";
}

function heightAndAirDesc(aircraft) {
  return `**Both sliders set to 0 dB:** showing height and atmospheric absorption alone on the 4.49° vs 5.5° paths (reset sliders to restore the ${aircraft} scenario values).`;
}

// Shared wording for the certificate and Reagan National scenarios. The text ends just before the aircraft difference.
function modelDesc({ aircraft, kind, text, sourceDelta, thrustDelta, note }) {
  if (!hasAdjustments()) return heightAndAirDesc(aircraft);
  return `**${kind}.** ${text} **${signed(sourceDelta, 2)} dB**. An estimated **${signed(thrustDelta, 1)} dB** thrust difference is added.${note}${slidersChangedNote()}`;
}

function altitudeFigure() {
  return state.runway === "27" ? "Fig. 9, p.23" : "Fig. 8, p.22";
}

function listenerNote() {
  const turn = state.runway === "09" ? " Beyond about 4 nm RWY 09 arrivals are turning, so the straight line is a simplification." : "";
  const site = currentScenario().site;
  const where = site ? `**Listener.** ${site.lateralM} m beside the path, using the straight-line distance from the aircraft when abeam` : "**Listener.** Directly below the path";
  return `${where}, flat ground. Place names are approximate.${turn}`;
}

function modelSources() {
  const correction = state.runway === "27" ? "its 1 nm label of 574 ft corrected to 547 ft" : "its 1,692 ft label replaced by slope value 1,656 ft";
  return [
    `**Flight paths.** Altitudes (ft AMSL): LCY Consultation ${altitudeFigure()} (${correction}). Runway elevation is ${RUNWAY_ELEVATION_FT} ft AMSL (Consultation p.11) and threshold crossing heights are 35 ft on 5.5° and 50 ft on 4.49° above threshold (Stage 2 pp.50, 61), giving 55 and 70 ft AMSL; acoustic distances use height above the ${RUNWAY_ELEVATION_FT} ft runway plane.`,
    ...MODEL_NOTES,
    listenerNote()
  ];
}

// The sliders at 0 show height and air alone
function heightAndAirSources() {
  return [
    ...modelSources(),
    "**Sliders at 0.** This is height and air alone. If other types flew 4.49°, the airport estimates under 2 dB from height (LCY Annex C p.41); the Stage 4 draft rule (p.33) limits it to authorised A320neo operators."
  ];
}

function thrustSources(thrustDelta, slopeBasis) {
  return [
    `**Thrust: ${signed(thrustDelta, 1)} dB, an estimate, not a measurement.** It starts from constant speed and drag, and Doc 29 approach NPD slopes from the 2015 ANP data (Directive pp.747, 753, 793), which has no neo, PW1500G or PW1900G tables. ${slopeBasis}`,
    `**Spoilers.** Spoiler drag on the 5.5° approach would lower it: if spoilers cancelled all of that aircraft's relief, the A320's 1,000 ft NPD slope leaves about **−0.45 dB** (about −1.0 dB LAmax at 400 ft, −0.1 to −0.3 dB at 4,000 ft, Directive pp.753, 793).`,
    `**Where thrust applies.** Only up to **${THRUST_ESTIMATE_END_NM} nm**, or the 5.5° top of descent if nearer, because Doc 29 default profiles put the A320 on landing flap from about 1,820 ft and the E190 from 1,500 ft (Directive pp.198, 221). From 2.5 to 3.7 nm the E190 may still be at idle, so the difference could be larger. London City's profiles are custom (Annex C p.8) and may differ from these defaults.`,
    `**Beyond that.** The hatched area has no thrust estimate: the thin line leaves thrust out, while the shaded range keeps the full thrust band until the 5.5° top of descent. Beyond that, where the ${baselineAircraft()} is level and the A320neo still descending, the thrust range becomes ${signed(LEVEL_VS_DESCENDING_DB, 0)} to 0 dB with no 5.5° relief (at 4,000 ft, level vs descending is 73 vs 71 dB SEL for the E190 and 69–74 vs 68–72 for new-generation types, Consultation Fig. 22, p.32; an SEL figure with no turboprops, used here in both metrics); beyond the 4.49° top of descent, where both are level, it narrows to ±0.45 dB, **a judgement** because no source gives a level-flight thrust difference. The shaded range steps at each top of descent because the evidence changes there, not the noise.`
  ];
}

// ---------------------------------------------------------------------------
// Scenario types
// ---------------------------------------------------------------------------

// The airport's own comparison of the A320neo with one other type
function airportScenario(aircraft, { basis, howBuilt = `The ${aircraft} is adjusted to fit London City's noise monitors` }) {
  return {
    name: `Airport: ${aircraft}`,
    kind: "LCY modelled",
    tone: "airport",
    tip: `The airport's own computer model (AEDT), not a measurement. ${howBuilt}; the A320neo, which can't yet land there, isn't adjusted to any measurement. SEL only, 0.5–5 km.`,
    baseline: aircraft,
    usesAirportTable: true,
    desc: () => `**Modelled by the airport, not measured.** Its computer model's figure for the A320neo at 4.49° vs the ${aircraft} at 5.5°, including height, aircraft and thrust. SEL only, published from 0.5 to 5 km (LCY consultation Figs. 17–18, pp.30–31).`,
    sources: () => [
      `**Airport model.** AEDT 3g model, **not measured**. ${basis} A320neo: unadjusted AEDT data on LCY profile at 4.49° (Annex C pp.8, 12).`,
      "**Published range.** From **0.5 to 5.0 km** (0.27–2.70 nm) only (Consultation pp.30–31).",
      "**Level flight.** Before descent, Consultation Fig. 22 (p.32) gives **80 vs 77–81 dB SEL at 2,000 ft** and **75 vs 72–77 dB SEL at 3,000 ft** (E190 vs new-generation types).",
      "**Not published.** Thrust and weight are estimated internally by AEDT, with no values, flap, gear or weather settings published (Annex C p.7)."
    ]
  };
}

// Approach certificates (measured at 3.0°) against one other type: A320neo at its lowest listed landing mass,
// 66.3 t (92.0–92.7 across both engines, midpoint 92.35 EPNdB), minus the other type's 3.0° certificate,
// plus the estimated thrust difference between 3°→5.5° (baseline) and 3°→4.49° (A320neo).
function certificateScenario(aircraft, { certificate, landingMass, sourceDelta, thrustDelta, slopeBasis, note = "", descNote = "", tipNote = "" }) {
  const kind = "EPNdB certificate proxy";
  return {
    name: `EASA: ${aircraft}`,
    kind,
    tone: "certificates",
    tip: `Uses the official EPNdB certificates of the A320neo and the ${aircraft}, from 3° test approaches at certified weights. Their EPNdB difference is treated as a dB(A) proxy; there is no validated conversion here to LAmax or SEL, and this is not a measurement at London City.${tipNote} ${MODELLED_ON_TOP}`,
    baseline: aircraft,
    desc: () => modelDesc({
      aircraft,
      kind,
      text: `From EASA noise certificates, on a 3° test approach: A320neo 92.0–92.7 EPNdB (midpoint 92.35) at 66.3 t vs ${certificate} EPNdB at ${landingMass}. Treating that EPNdB gap as a dB(A) proxy gives an assumed aircraft difference of`,
      sourceDelta,
      thrustDelta,
      note: descNote
    }),
    sourceDelta,
    thrustDelta,
    sources: () => [
      ...modelSources(),
      `**Where the certificates are.** A320neo, EASA A320 sheet p.175 (LEAP-1A) and p.226 (PW1100G); ${aircraft}, ${CERTIFICATE_SOURCES[aircraft]}.`,
      `**Certificate limits.** Certificates are in EPNdB at **3° test conditions** and certified landing masses, not London City's angles or weights. **There is no validated conversion here from an EPNdB difference to a dB(A), LAmax or SEL difference**: the model uses that gap only as an explicit proxy. EPNdB adds tone corrections and a different frequency weighting, and includes approach-speed duration (−10 log(V_A320 / V_base), about −0.2 dB against the E190 from Doc 29 speed coefficients and unknown for types Doc 29 doesn't list, shared by SEL but absent from peak LAmax, Directive pp.122, 153, 166). 66.3 t is the lowest listed A320neo landing mass; higher certified masses (67.4 and 68.4 t, up to 92.9 EPNdB, EASA A320 sheet pp.175, 226) add up to +0.2 dB in the evidence band, and London City's quota scheme uses average MTOW rather than lowest mass (noise scheme p.10). No document gives typical London City landing weights; the midpoint is a simple choice for an unknown engine, and the sources don't say which E190 modifications or A320neo engine would be used there.`,
      ...aboutThisAircraft(note),
      ...thrustSources(thrustDelta, slopeBasis)
    ]
  };
}

// Arrivals measured at Reagan National on typical approach angles, in place of the certificate difference
function reaganScenario(aircraft, { aefPage, sourceDelta, thrustDelta, slopeBasis, note, descNote = "", tipNote = "" }) {
  const kind = "Measured at Reagan National, US";
  return {
    name: `Measured: ${aircraft}`,
    kind,
    tone: "measured",
    tip: `Real arrivals of both the A320neo and the ${aircraft}, measured at a US airport on typical approach angles, not at London City.${tipNote} The LAmax difference is used for SEL too. ${MODELLED_ON_TOP}`,
    wide: true,
    baseline: aircraft,
    desc: () => modelDesc({
      aircraft,
      kind,
      text: `Real arrivals of both aircraft (AEF report, p.${aefPage}): A320neo minus ${aircraft} in LAmax is`,
      sourceDelta,
      thrustDelta,
      note: descNote
    }),
    sourceDelta,
    thrustDelta,
    sources: () => [
      ...modelSources(),
      `**Measurement.** ${note}`,
      "**Measurement limits.** **Measured at a US airport** on typical approach angles, with aircraft weights, engine variants and flight settings not reported. Applying a peak LAmax difference to SEL omits any approach-speed duration difference: about 0.2 dB in the faster A320neo's favour against the E190, and unknown against the A220, which Doc 29 doesn't list (Directive pp.122, 153, 166). The monitors are 3.1–7.1 km from the airport, and applying that figure inward to 0.5 km may understate A320neo minus E190 near the runway if the E190's spectrum decays more slowly with distance.",
      ...thrustSources(thrustDelta, slopeBasis)
    ]
  };
}

// E190 minus another type in the current metric, rounded because the sources give one decimal
function measuredGap(levels, aircraft) {
  return Number((levels.E190[state.metric] - levels[aircraft][state.metric]).toFixed(1));
}

// A320neo minus another type = (A320neo minus E190) + (E190 minus that type, measured at monitor 6).
// Monitor 6 measures both types on the 5.5° approach, so only the E190's thrust estimate is still needed.
// The sliders and chart line start from the certificates; the description also gives the result from Reagan National.
function monitor6Scenario(aircraft, { note = "" } = {}) {
  const { flights, LAmax, SEL } = MONITOR_6[aircraft];
  const e190 = MONITOR_6.E190;
  const gap = () => measuredGap(MONITOR_6, aircraft);
  const resultFrom = (e190Delta, nm) => {
    const ac = getAcoustics(nm);
    return ac.geomDB + ac.atmDB + e190Delta + gap() + thrustDeltaAt(nm, E190_THRUST_DELTA);
  };
  return {
    name: `Hybrid Monitor 6: ${aircraft}`,
    kind: "Measured at London City + EPNdB certificate proxy",
    tone: "hybrid",
    tip: `Two steps. The E190 vs ${aircraft} gap is measured at London City's monitor 6, with both on the 5.5° approach (${flights} ${aircraft} arrivals). No A320neo has been measured there, so A320neo vs E190 uses the EPNdB certificate gap as a dB(A) proxy; there is no validated conversion to LAmax or SEL. Height and air are then modelled, and the E190's thrust is estimated.`,
    wide: true,
    baseline: aircraft,
    descFollowsProbe: true, // The description quotes results at the selected distance
    e190Gap: gap,
    gapPlace: "at monitor 6",
    thrustDelta: E190_THRUST_DELTA,
    get sourceDelta() {
      return Number((E190_CERTIFICATE_DELTA + gap()).toFixed(2));
    },
    desc: () => {
      if (!hasAdjustments()) return heightAndAirDesc(aircraft);
      const nm = state.probeNM;
      const results = insideFirstAssessmentPoint(nm)
        ? ""
        : ` At ${nm.toFixed(2)} nm that gives **${signed(resultFrom(E190_CERTIFICATE_DELTA, nm), 1)} dB**${slidersChanged() ? "" : " (the line shown)"}, or **${signed(resultFrom(E190_MEASURED_DELTA, nm), 1)} dB** using Reagan National measurements instead${hasThrustEstimate(nm) ? "" : ", leaving out thrust"}.`;
      return `**Measured at London City + EPNdB certificate proxy.** At monitor 6 the E190 measures **${gap().toFixed(1)} dB ${state.metric} louder** than the ${aircraft}. No A320neo has been measured there, so A320neo vs E190 uses the certificate gap as a dB(A) proxy (**${signed(E190_CERTIFICATE_DELTA, 2)} dB**); there is no validated conversion to ${state.metric}. Thrust is estimated at **${signed(E190_THRUST_DELTA, 1)} dB**.${results}${smallSampleNote(aircraft, flights)}${slidersChangedNote()}`;
    },
    sources: () => [
      ...modelSources(),
      `**Monitor 6 measurements.** E190 ${e190.LAmax} dB LAmax and ${e190.SEL} dB SEL from ${e190.flights} arrivals; ${aircraft} ${LAmax} dB LAmax and ${SEL} dB SEL from ${flights} arrivals (Bickerdike Allen Thamesmead survey, Table 3, p.8). RWY 27 arrivals overfly this monitor, 2 September to 8 October 2024. It measures both types at London City on the 5.5° approach, so it includes their real thrust and weights.`,
      `**Monitor 6 limits.** The gap is measured at **one place**, about 3 km from the threshold on the 5.5° descent, and is applied unchanged at every distance, including level flight beyond the top of descent, where a gap measured on the descent may not hold. The report gives no spread for these averages. **There are no A320neo figures**, so the A320neo minus E190 part comes from the EASA certificates (${signed(E190_CERTIFICATE_DELTA, 2)} dB) for the sliders and chart line, or from Reagan National arrivals (${signed(E190_MEASURED_DELTA, 2)} dB) for the second result.`,
      ...thrustSources(E190_THRUST_DELTA, `${E190_SLOPES} This is the E190's estimate: the ${aircraft}'s own thrust isn't estimated, because monitor 6 measured it.`),
      ...aboutThisAircraft(note)
    ]
  };
}

// A scenario worked out 500 m beside the path, added to the other type's level measured at the site to give an A320neo level.
// sourceDelta is a function because a bridged scenario's value depends on the metric. reaganDelta is the same difference
// from Reagan National, where one exists for that type. bridgeNote marks a scenario built through the E190.
function gardenScenario(aircraft, { sourceDelta, thrustDelta, slopeBasis, reaganDelta = null, bridgeNote = null }) {
  const garden = THAMESMEAD_GARDEN;
  const levels = garden.levels;
  const nm = garden.km / KM_PER_NM;
  const bridged = bridgeNote !== null;
  const flights = levels[aircraft].flights;
  const levelWith = delta => levels[aircraft][state.metric] + delta;
  const measuredAt = type => `${levels[type].LAmax.toFixed(1)} and ${levels[type].SEL.toFixed(1)} from ${levels[type].flights}`;
  return {
    name: `Hybrid Thamesmead garden: ${aircraft}`,
    kind: "LCY measured + EPNdB certificate proxy",
    tone: "site",
    tip: `Estimates an A320neo's level in a Thamesmead garden, 500 m beside the arrival path. It starts from the ${aircraft} level measured there in a survey for London City Airport${flights < SMALL_SAMPLE_FLIGHTS ? ` (only ${flights} arrivals)` : ""}, then adds ${bridged ? "the gap measured there to the E190 and the EPNdB certificate gap between the A320neo and the E190, used as a dB(A) proxy" : "the EPNdB certificate gap between the aircraft, used as a dB(A) proxy"}. There is no validated conversion to LAmax or SEL. Height and air are then modelled, and thrust is estimated. No A320neo has been measured there.`,
    wide: true,
    baseline: aircraft,
    site: { nm, lateralM: garden.lateralM },
    ...(bridged ? { e190Gap: () => measuredGap(levels, aircraft), gapPlace: "in the garden" } : {}),
    get sourceDelta() {
      return sourceDelta();
    },
    thrustDelta,
    desc: () => {
      if (!hasAdjustments()) return heightAndAirDesc(aircraft);
      const ac = getAcoustics(nm);
      const range = evidenceRangeAt(nm);
      const scenarioNet = ac.geomDB + ac.atmDB + sourceDelta() + thrustDeltaAt(nm, thrustDelta);
      const reagan = reaganDelta === null ? "" : `, or **${levelWith(ac.geomDB + ac.atmDB + reaganDelta() + thrustDeltaAt(nm, thrustDelta)).toFixed(1)}** using Reagan National`;
      const measured = Object.keys(levels).map(type => `${type} ${levels[type][state.metric].toFixed(1)}`).join(", ");
      const basis = bridged
        ? `**That is the E190-based estimate**, using an EPNdB certificate gap as a dB(A) proxy, compared here with the ${aircraft}'s level.`
        : `**That is an estimate**, using an EPNdB certificate gap as a dB(A) proxy, built on the ${aircraft}'s level.`;
      const lead = slidersChanged()
        ? `At the current sliders, an A320neo arriving on RWY 27 reaches **${levelWith(ac.netDB).toFixed(1)} dB ${state.metric}** in the garden, vs **${levelWith(scenarioNet).toFixed(1)}** from the scenario values (evidence range **${levelWith(range.low).toFixed(1)} to ${levelWith(range.high).toFixed(1)}**)${reagan}.`
        : `An A320neo arriving on RWY 27 would likely reach about **${levelWith(scenarioNet).toFixed(1)} dB ${state.metric}** in the garden (range **${levelWith(range.low).toFixed(1)} to ${levelWith(range.high).toFixed(1)}**)${reagan}.`;
      return `**LCY measured + EASA certificates.** ${lead} ${basis}${smallSampleNote(aircraft, flights)} Averages measured there: ${measured}. This is an **average flight**, not the loudest. Departures are louder there and aren't estimated. The chart shows a listener 500 m beside the path; the marked point is the garden.${slidersChangedNote()}`;
    },
    sources: () => [
      ...modelSources(),
      `**Measured at the site.** Thamesmead survey site, measured for London City Airport by Bickerdike Allen, 2 September to 8 October 2024 (Bickerdike Allen Thamesmead survey, Table 1, p.6): **E190 ${levels.E190.LAmax.toFixed(1)} dB LAmax and ${levels.E190.SEL.toFixed(1)} dB SEL** from ${levels.E190.flights} arrivals; A220-100 ${measuredAt("A220")}; E190-E2 ${measuredAt("E190-E2")}; Dash 8-Q400 ${measuredAt("Dash 8-Q400")}. The report gives no spread.`,
      "**Where it is.** Around **4 km** from the RWY 27 threshold and around **500 m** north of the arrival path, and RWY 09 arrivals don't fly near it (Bickerdike Allen, pp.4–5), so this scenario is RWY 27 only.",
      bridged
        ? `**How the estimate works.** The A320neo level is the ${aircraft}'s measured level plus the modelled difference, and **hasn't been measured**. That difference is the gap to the E190 measured in the garden, plus the EASA: E190 scenario's EPNdB certificate gap used as a dB(A) proxy and its thrust estimate; neither is specific to a listener beside the path. The A320neo level therefore comes out the same as in the E190's garden scenario: this scenario changes what it is compared with, and isn't a second estimate of it. The gap is measured on the 5.5° descent and applied at every distance, including level flight beyond the top of descent, where it may not hold.`
        : `**How the estimate works.** The A320neo level is the ${aircraft}'s measured level plus the modelled difference, and **hasn't been measured**. The aircraft difference is the EASA: ${aircraft} EPNdB certificate gap used as a dB(A) proxy; there is no validated conversion to LAmax or SEL. The thrust difference is estimated. Neither is specific to a listener beside the path.`,
      "**Left out.** Doc 29 lateral attenuation isn't included; it would lower the difference by about 0.1 dB, because the lower A320neo is seen at a shallower angle (Directive p.80). In SEL, quieter events at the garden may be cut short by the monitor's event threshold, which the report doesn't give: SEL minus LAmax tends to be smaller for quieter types, at 9.9 dB on the 63.0 dB E190 and 8.5 dB on the 59.8 dB Dash 8-Q400 (Bickerdike Allen, Table 1, p.6), against 9.0 and 9.7 dB at monitor 6 (Table 3, p.8). If so, measured SEL gaps are too wide. Departures fly over the site, measuring E190 74.8 dB LAmax and 84.5 dB SEL (Bickerdike Allen, Table 2, p.6), but aren't part of this model.",
      ...thrustSources(thrustDelta, slopeBasis),
      ...aboutThisAircraft(bridgeNote)
    ]
  };
}

// The garden scenario with the same aircraft and thrust differences as the type's certificate scenario
function certificateGardenScenario(aircraft, { sourceDelta, thrustDelta, slopeBasis, reaganDelta = null }) {
  return gardenScenario(aircraft, {
    sourceDelta: () => sourceDelta,
    thrustDelta,
    slopeBasis,
    reaganDelta: reaganDelta === null ? null : () => reaganDelta
  });
}

// For a type whose certificates contradict what was measured at the site: A320neo minus E190 from the certificates,
// plus the E190 vs that type gap measured in the garden. The A320neo level comes out the same as from the E190.
function bridgedGardenScenario(aircraft, { note }) {
  const fromE190 = e190Delta => Number((e190Delta + measuredGap(THAMESMEAD_GARDEN.levels, aircraft)).toFixed(2));
  return gardenScenario(aircraft, {
    sourceDelta: () => fromE190(E190_CERTIFICATE_DELTA),
    thrustDelta: E190_THRUST_DELTA,
    slopeBasis: `${E190_SLOPES} This is the E190's estimate: the ${aircraft}'s own thrust isn't estimated, because both were measured at the site.`,
    reaganDelta: () => fromE190(E190_MEASURED_DELTA),
    bridgeNote: note
  });
}

// ---------------------------------------------------------------------------
// The scenarios, grouped by aircraft in the sidebar
// ---------------------------------------------------------------------------

const SCENARIOS = [
  airportScenario("E190", {
    basis: "E190: 737-500 data **+1.5 dB**, fitted at London City noise monitors 1–6 (LCY Annex C pp.9–10). The 3–5 km drop may come from a flap step in that data (1,000 ft in the Doc 29 default profile, Directive p.189), but Annex C's profiles are custom (p.8), so this is an inference."
  }),
  certificateScenario("E190", {
    ...E190_ESTIMATE,
    certificate: "E190 92.5",
    landingMass: "43 t",
    note: "E190 92.5: the airport's example (noise scheme p.33); 92.4 records are Chapter 3 only. The 91.8 EPNdB records require a Flap 06 inhibitor (EASA ERJ 190 sheet p.39) and are left out of the default, but no source here says which flap setting London City's E190s use: they would give +0.55 dB. Reagan National arrivals measured **about −2 dB LAmax** (AEF Table 5, p.8)."
  }),
  reaganScenario("E190", {
    aefPage: 8,
    sourceDelta: E190_MEASURED_DELTA,
    thrustDelta: E190_THRUST_DELTA,
    slopeBasis: E190_SLOPES,
    note: "A320neo minus E190: **−2.2, −2.0 and −1.8 dB LAmax** at monitors 6, 8 and 17, from 545/180, 959/309 and 26/8 arrivals over 6 months in 2024–25 (AEF Table 5, p.8)."
  }),
  certificateGardenScenario("E190", { ...E190_ESTIMATE, reaganDelta: E190_MEASURED_DELTA }),

  airportScenario("E190-E2", { basis: "E190-E2: EMB190 data **−0.9 dB** (LCY Annex C p.10)." }),
  certificateScenario("E190-E2", { ...E190_E2_ESTIMATE, certificate: "E190-E2 91.4", landingMass: "49.05 t" }),
  monitor6Scenario("E190-E2"),
  certificateGardenScenario("E190-E2", E190_E2_ESTIMATE),

  airportScenario("E195-E2", {
    basis: `E195-E2: based on the E190-E2 with an allowance for its larger size (LCY Annex C p.11). ${E195_FORECAST}`,
    howBuilt: "The E195-E2 is based on the E190-E2, allowing for its larger size"
  }),
  certificateScenario("E195-E2", {
    certificate: "E195-E2 91.7",
    landingMass: "54.0 t",
    sourceDelta: 0.65,
    thrustDelta: 0.2,
    slopeBasis: E195_E2_SLOPES,
    note: E195_FORECAST
  }),

  airportScenario("A220", {
    basis: "A220-100: 737-500 data **−1.5 dB** (LCY Annex C p.10). Its table differs from the E190's by exactly 3.0 dB because both use that 737-500 data."
  }),
  certificateScenario("A220", {
    ...A220_ESTIMATE,
    certificate: "A220-100 91.9",
    landingMass: "54.7 t",
    note: "Reagan National arrivals measured **+2.5 dB LAmax** (AEF Table 6, p.9). **The sources disagree on the E190–A220 gap:** about 4.7 dB measured at Reagan National, 0.5 dB LAmax and 0.1 dB SEL at London City's monitor 6, 3.0 dB in the airport's tables, 0.6 dB on EASA certificates."
  }),
  monitor6Scenario("A220"),
  reaganScenario("A220", {
    aefPage: 9,
    sourceDelta: 2.5,
    thrustDelta: 0.2,
    slopeBasis: A220_SLOPES,
    note: "A320neo minus A220: **62.0 vs 59.5 dB LAmax** at monitor 6, **19 arrivals each** in January 2022, which AEF calls a snapshot (Table 6, p.9). The same monitor gives the E190's −2.2 dB, and its A320neo level is similar in both periods (62.0 and 62.8 dB). AEF notes that A220s at London City may be quieter because of their lower take-off weight (p.9). This figure implies the E190 is about 4.7 dB louder than the A220, while London City's monitor 6 measures 0.5 dB LAmax, so treat it with caution.",
    descNote: " **Small sample:** 19 arrivals each in one month, and London City's monitor 6 shows a much smaller E190–A220 gap.",
    tipNote: " Only 19 arrivals each, in one month."
  }),
  certificateGardenScenario("A220", { ...A220_ESTIMATE, reaganDelta: 2.5 }),

  certificateScenario("Dash 8-Q400", {
    certificate: "Dash 8-Q400 94.9",
    landingMass: "27.4 t",
    sourceDelta: -2.55,
    thrustDelta: -0.1,
    slopeBasis: Q400_SLOPES,
    note: `Dash 8-Q400 94.9: Chapter 14 record with no added procedure. The 93.0 record needs the 850 rpm approach (AFM Supplement 39), and no source here says which London City's use: it would give −0.65 dB. ${Q400_NOTE}`,
    descNote: " **Likely too low:** certificates put the Dash 8-Q400 louder than the E190, but London City measured it about 3 dB quieter, so Hybrid Monitor 6 is the better guide for this aircraft.",
    tipNote: " Likely too low for this aircraft: London City's measurements put it well below what its certificates suggest."
  }),
  monitor6Scenario("Dash 8-Q400", { note: Q400_NOTE }),
  bridgedGardenScenario("Dash 8-Q400", {
    note: `Built through the E190 because its certificates would put the A320neo 6–7.5 dB below the E190-based estimate at the same site. ${Q400_NOTE}`
  })
];

/**
 * The page around the charts: wiring up the controls in index.html, keeping them and the readout
 * in step with the state, and moving the line on the charts with the pointer and keyboard.
 */

const CLICK_SLOP_PX = 4; // Further than this between press and release is a drag

let sourceSlider, thrustSlider;
const adjustedSource = {}; // Aircraft Δ the viewer has set, by scenario
const adjustedThrust = {}; // Thrust Δ the viewer has set, by scenario
let probePress = null;     // Where and how the pointer last went down on the charts, to tell a click from a drag or a tap
let announceTimer = null;

function byId(id) {
  return document.getElementById(id);
}

function refresh() {
  syncControls();
  redraw();
}

// ---------------------------------------------------------------------------
// Wiring up the page
// ---------------------------------------------------------------------------

function setupControls() {
  setupSliders();
  setupScenarioButtons();
  setupToggles();

  byId("fullscreen-btn").addEventListener("click", () => fullscreen(!fullscreen()));
  document.addEventListener("fullscreenchange", () => {
    byId("fullscreen-btn").textContent = document.fullscreenElement ? "Exit full screen" : "Full screen";
  });
}

function setupSliders() {
  sourceSlider = byId("source-slider");
  thrustSlider = byId("thrust-slider");
  sourceSlider.min = SOURCE_SLIDER.min;
  sourceSlider.max = SOURCE_SLIDER.max;
  thrustSlider.min = THRUST_SLIDER.min;
  thrustSlider.max = THRUST_SLIDER.max;

  sourceSlider.addEventListener("input", () => {
    state.sourceDelta = adjustedSource[state.scenarioIndex] = Number(sourceSlider.value);
    refresh();
  });
  thrustSlider.addEventListener("input", () => {
    state.thrustDelta = adjustedThrust[state.scenarioIndex] = Number(thrustSlider.value);
    refresh();
  });

  byId("reset-sliders").addEventListener("click", () => {
    delete adjustedSource[state.scenarioIndex];
    delete adjustedThrust[state.scenarioIndex];
    applyScenario(state.scenarioIndex);
  });
}

function setSliders(sourceDelta, thrustDelta) {
  state.sourceDelta = sourceDelta;
  state.thrustDelta = thrustDelta;
  sourceSlider.value = sourceDelta;
  thrustSlider.value = thrustDelta;
}

function applyScenario(index) {
  state.scenarioIndex = index;
  const scenario = currentScenario();
  if (scenario.site) state.runway = "27"; // The site is only near the RWY 27 arrival path
  // The airport's single net figure ignores the sliders, so they're left alone until a model scenario sets them
  if (!scenario.usesAirportTable) {
    setSliders(adjustedSource[index] ?? scenario.sourceDelta, adjustedThrust[index] ?? scenario.thrustDelta);
  }
  refresh();
}

function setupScenarioButtons() {
  let group;
  SCENARIOS.forEach((scenario, index) => {
    if (scenario.baseline !== SCENARIOS[index - 1]?.baseline) group = addScenarioGroup(scenario.baseline);
    const button = document.createElement("button");
    button.type = "button";
    const name = document.createElement("span");
    name.className = "scenario-name";
    name.textContent = scenario.name.replace(`: ${scenario.baseline}`, ""); // The heading above names the aircraft
    const kind = document.createElement("span");
    kind.className = "scenario-kind";
    kind.textContent = scenario.kind;
    button.append(name, kind);
    button.classList.toggle("is-wide", scenario.wide === true);
    button.classList.add(`tone-${scenario.tone}`);
    addScenarioTip(button, scenario, index);
    button.addEventListener("click", () => {
      if (scenario.site && !state.probePinned) state.probeNM = scenario.site.nm; // A pinned line stays put, to compare scenarios at one distance
      applyScenario(index);
    });
    group.appendChild(button);
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape") hideScenarioTip();
  });
  document.querySelector(".controls").addEventListener("scroll", hideScenarioTip);
}

// An aircraft's heading in the scenario list, returning the grid its buttons go in
function addScenarioGroup(aircraft) {
  const heading = document.createElement("h3");
  heading.id = `scenario-group-${aircraft}`;
  heading.textContent = `A320neo vs ${aircraft}`;
  const grid = document.createElement("div");
  grid.className = "scenario-grid";
  grid.setAttribute("role", "group");
  grid.setAttribute("aria-labelledby", heading.id);
  byId("scenarios").append(heading, grid);
  return grid;
}

// The hover note on a scenario button. Screen readers get the same text through a hidden description.
function addScenarioTip(button, scenario, index) {
  const description = document.createElement("span");
  description.id = `scenario-tip-${index}`;
  description.hidden = true;
  description.textContent = scenario.tip;
  button.append(description);
  button.setAttribute("aria-describedby", description.id);

  button.addEventListener("pointerenter", event => {
    if (event.pointerType !== "touch") showScenarioTip(button, scenario);
  });
  button.addEventListener("pointerleave", hideScenarioTip);
  button.addEventListener("focus", () => {
    if (button.matches(":focus-visible")) showScenarioTip(button, scenario);
  });
  button.addEventListener("blur", hideScenarioTip);
  button.addEventListener("click", hideScenarioTip); // The description below now says the same
}

// Beside the scenario list when there's room, otherwise under the button (or above it, near the bottom of the window)
function showScenarioTip(button, scenario) {
  const tip = byId("scenario-tip");
  const heading = document.createElement("strong");
  heading.textContent = scenario.kind;
  tip.replaceChildren(heading, scenario.tip);
  tip.hidden = false;

  const margin = 8;
  const buttonBox = button.getBoundingClientRect();
  const listRight = byId("scenarios").getBoundingClientRect().right;
  const tipW = tip.offsetWidth;
  const tipH = tip.offsetHeight;
  let left = listRight + 2 * margin;
  let top = buttonBox.top;
  if (left + tipW > window.innerWidth) {
    left = buttonBox.left;
    top = buttonBox.bottom + margin;
    if (top + tipH > window.innerHeight - margin) top = buttonBox.top - tipH - margin;
  }
  tip.style.left = `${constrain(left, margin, window.innerWidth - tipW - margin)}px`;
  tip.style.top = `${constrain(top, margin, window.innerHeight - tipH - margin)}px`;
}

function hideScenarioTip() {
  byId("scenario-tip").hidden = true;
}

function setupToggles() {
  document.querySelectorAll("[data-runway]").forEach(button => {
    button.addEventListener("click", () => {
      state.runway = button.dataset.runway;
      refresh();
    });
  });
  document.querySelectorAll("[data-metric]").forEach(button => {
    button.addEventListener("click", () => {
      state.metric = button.dataset.metric;
      applyScenario(state.scenarioIndex); // Monitor 6 scenarios have a different value in each metric
    });
  });
}

// The divider beside the settings panel: drag it, or use the arrow keys when it's focused.
// The chart follows through its ResizeObserver, and the width is remembered in this browser.
function setupSidebarResizer() {
  const SIDEBAR_MIN = 320; // Narrower breaks the scenario labels at their hyphens
  const CHARTS_MIN = 600; // Narrower makes the plots too small to read. Also in the layout's columns in style.css.
  const KEY_STEP = 24;
  const STORAGE_KEY = "noise-sidebar-width";

  const layout = document.querySelector(".layout");
  const sidebar = document.querySelector(".controls");
  const handle = byId("sidebar-resizer");
  const widest = () => Math.max(SIDEBAR_MIN, layout.clientWidth - handle.offsetWidth - CHARTS_MIN);

  const announce = () => {
    handle.setAttribute("aria-valuemin", SIDEBAR_MIN);
    handle.setAttribute("aria-valuemax", widest());
    handle.setAttribute("aria-valuenow", sidebar.offsetWidth);
  };

  const remember = value => {
    try {
      if (value === null) localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, value);
    } catch (error) {
      // Storage can be blocked. The panel still resizes, it just won't be remembered.
    }
  };

  const setWidth = px => {
    const next = Math.round(constrain(px, SIDEBAR_MIN, widest()));
    layout.style.setProperty("--sidebar-width", `${next}px`);
    remember(next);
    announce();
  };

  let saved = null;
  try {
    saved = Number(localStorage.getItem(STORAGE_KEY));
  } catch (error) {
    // As above: start from the default width
  }
  if (saved >= SIDEBAR_MIN) layout.style.setProperty("--sidebar-width", `${saved}px`);
  announce();
  new ResizeObserver(announce).observe(layout);

  handle.addEventListener("pointerdown", event => {
    if (event.button === 0) handle.setPointerCapture(event.pointerId);
  });
  handle.addEventListener("pointermove", event => {
    if (!handle.hasPointerCapture(event.pointerId)) return;
    setWidth(event.clientX - layout.getBoundingClientRect().left - handle.offsetWidth / 2);
  });
  handle.addEventListener("dblclick", () => {
    layout.style.removeProperty("--sidebar-width");
    remember(null);
    announce();
  });
  handle.addEventListener("keydown", event => {
    const current = sidebar.offsetWidth;
    const targets = {
      ArrowLeft: current - KEY_STEP,
      ArrowRight: current + KEY_STEP,
      Home: SIDEBAR_MIN,
      End: widest()
    };
    if (!(event.key in targets)) return;
    event.preventDefault();
    setWidth(targets[event.key]);
  });
}

function setupCanvas(canvas, chartBox) {
  const element = canvas.elt;
  element.tabIndex = 0;
  element.setAttribute("role", "img");
  element.setAttribute("aria-label", CANVAS_DESCRIPTION);
  element.addEventListener("pointermove", movePointer);
  element.addEventListener("pointerdown", movePointer);
  element.addEventListener("pointerdown", rememberProbePress);
  element.addEventListener("click", toggleProbePin);
  element.addEventListener("keydown", moveProbeWithKeys);

  // The chart area changes size with the window, the sidebar's width and its stacking
  new ResizeObserver(() => {
    if (chartBox.clientWidth !== width || chartBox.clientHeight !== height) {
      resizeCanvas(chartBox.clientWidth, chartBox.clientHeight);
    }
  }).observe(chartBox);
}

// ---------------------------------------------------------------------------
// Keeping the controls in step with the state
// ---------------------------------------------------------------------------

function syncControls() {
  const airport = usingAirportTable();
  const scenario = currentScenario();

  syncToggles(scenario, airport);
  setCitedText(byId("scenario-desc"), scenario.desc());
  syncSliders(airport);
  syncEvidence();
  syncLabels();

  const sources = airport || hasAdjustments() ? scenario.sources() : heightAndAirSources();
  byId("sources").replaceChildren(...sources.map(line => {
    const paragraph = document.createElement("p");
    setCitedText(paragraph, line);
    return paragraph;
  }));

  document.body.classList.toggle("is-airport", airport);
  document.body.classList.toggle("is-site", Boolean(scenario.site));
}

function setPressed(button, pressed) {
  button.setAttribute("aria-pressed", pressed ? "true" : "false");
}

function syncToggles(scenario, airport) {
  byId("scenarios").querySelectorAll("button").forEach((button, i) => setPressed(button, i === state.scenarioIndex));
  document.querySelectorAll("[data-runway]").forEach(button => {
    setPressed(button, button.dataset.runway === state.runway);
    button.disabled = Boolean(scenario.site) && button.dataset.runway !== "27";
  });
  document.querySelectorAll("[data-metric]").forEach(button => {
    setPressed(button, button.dataset.metric === currentMetric());
    button.disabled = airport;
  });
  byId("metric-hint").textContent = airport
    ? "The airport's comparison tables give SEL only."
    : (state.metric === "LAmax" ? "Loudest moment of the flyover (20 log)." : "Total sound energy of the flyover (10 log).");
}

function syncSliders(airport) {
  byId("reset-sliders").hidden = airport || !slidersChanged();

  // The airport's single net figure already contains source and thrust
  byId("slider-note").hidden = !airport;
  byId("source-evidence").hidden = airport;
  byId("thrust-evidence").hidden = airport;
  for (const slider of [sourceSlider, thrustSlider]) {
    slider.disabled = airport;
    slider.closest(".field").classList.toggle("is-disabled", airport);
  }
  const showValue = (slider, output, valueText) => {
    output.textContent = airport ? "In LCY figure" : valueText;
    slider.setAttribute("aria-valuetext", airport ? "Included in airport figure" : valueText);
  };
  showValue(sourceSlider, byId("source-value"), `${signed(state.sourceDelta, 2)} dB`);
  showValue(thrustSlider, byId("thrust-value"), `${signed(state.thrustDelta, 1)} dB`);
}

function syncEvidence() {
  const placeBand = (element, range, slider) => {
    const toPercent = value => ((value - slider.min) / (slider.max - slider.min)) * 100;
    element.style.left = `${toPercent(range[0])}%`;
    element.style.width = `${toPercent(range[1]) - toPercent(range[0])}%`;
  };
  const evidence = activeEvidence();
  placeBand(byId("band-source"), evidence.source.range, SOURCE_SLIDER);
  byId("source-evidence-text").textContent = evidence.source.text;
  placeBand(byId("band-thrust"), evidence.thrust.range, THRUST_SLIDER);
  byId("thrust-evidence-text").textContent = evidence.thrust.text;
}

function syncLabels() {
  const baseline = baselineAircraft();
  byId("subtitle").textContent = baseline === "E190"
    ? "Today's most common aircraft, the E190 at 5.5°, compared with the A320neo, new to the airport, at the proposed 4.49°"
    : `The ${baseline} at 5.5° compared with the A320neo, new to the airport, at the proposed 4.49°`;
  byId("r-curr-label").textContent = `${baseline} altitude (5.5° AMSL)`;
  byId("source-label").textContent = `Aircraft Δ: A320neo minus ${baseline}`;
  byId("thrust-label").textContent = `Thrust Δ: A320neo minus ${baseline}`;
}

// ---------------------------------------------------------------------------
// The readout above the charts, at the selected distance
// ---------------------------------------------------------------------------

function updateReadout() {
  const scenario = currentScenario();
  const nm = state.probeNM;
  if (scenario.descFollowsProbe) setCitedText(byId("scenario-desc"), scenario.desc());

  const ac = getAcoustics(nm);
  const airport = probeAirportValues(nm);
  const tooClose = insideFirstAssessmentPoint(nm);
  const noThrust = !airport && hasAdjustments() && !hasThrustEstimate(nm);

  byId("r-distance").textContent = `${nm.toFixed(2)} nm · ${(nm * KM_PER_NM).toFixed(2)} km`;
  byId("chart-hint").textContent = chartHint();
  byId("r-curr").textContent = feet(ac.currAlt);
  byId("r-prop").textContent = feet(ac.propAlt);
  byId("r-drop").textContent = `${signed(-Math.round(ac.deltaFt), 0)} ft`;

  showComponent(byId("r-geom"), tooClose ? null : ac.geomDB + ac.atmDB);
  showComponent(byId("r-source"), tooClose ? null : ac.sourceDB + ac.thrustDB, noThrust ? " (no thrust)" : "");
  showEvidenceRange(!airport && !tooClose && hasAdjustments() ? evidenceRangeAt(nm) : null);

  if (airport && !airport.predicted) {
    showNoFigure("Airport prediction (0.5–5 km only)", "Outside 0.5–5 km table", "");
  } else if (!airport && tooClose) {
    showNoFigure("Ground noise (< 0.5 km)", "No estimate", "The airport's tables start at 0.5 km, so no estimate is plotted closer to the threshold");
  } else {
    showNetFigure(airport ? airport.db : ac.netDB, Boolean(airport), noThrust);
  }
}

function chartHint() {
  if (state.probePinned) {
    const site = currentScenario().site;
    const away = site && Math.abs(state.probeNM - site.nm) >= 0.005 ? ` This scenario's estimate is for its site at ${site.nm.toFixed(2)} nm.` : "";
    return `Line pinned at ${state.probeNM.toFixed(2)} nm.${away} Click the charts or press Enter to unpin it. Arrow keys nudge it when the chart is focused.`;
  }
  return window.matchMedia("(hover: hover)").matches
    ? "Move across the charts to read any distance, and click to pin the line. When the chart is focused, arrow keys also move it and Enter pins it."
    : "Drag across the charts or tap to read any distance.";
}

function showComponent(element, db, suffix = "") {
  element.textContent = db === null ? "—" : `${signed(db, 1)} dB${suffix}`;
  element.title = db === null ? "" : `${signed(db, 2)} dB unrounded`;
}

function showEvidenceRange(range) {
  byId("r-range").textContent = range ? `${signed(range.low, 1)} to ${signed(range.high, 1)} dB` : "—";
  const round1 = value => Math.sign(value) * (Math.round((Math.abs(value) + 1e-12) * 10) / 10);
  const low = range ? round1(range.low) : 0;
  const high = range ? round1(range.high) : 0;
  const crossed = range ? [-NOTICEABLE_DB, 0, NOTICEABLE_DB].filter(level => low < level && high > level) : [];
  byId("r-range-note").textContent = crossed.length
    ? `Range crosses ${crossed.map(level => (level === 0 ? "no change" : `${signed(level, 0)} dB`)).join(", ").replace(/, ([^,]*)$/, " and $1")}`
    : "";
}

function showNoFigure(label, value, title) {
  byId("r-net-label").textContent = label;
  const net = byId("r-net");
  net.textContent = value;
  net.title = title;
  byId("r-chip").hidden = true;
}

function showNetFigure(db, airport, noThrust) {
  const pair = `A320neo minus ${baselineAircraft()}`;
  // A site scenario has a different listener, which a comparison at one distance needs to show
  const site = currentScenario().site;
  byId("r-net-label").textContent = airport
    ? `Airport prediction, ${pair}`
    : [pair, noThrust && "leaving out thrust", site && `${site.lateralM} m beside the path`].filter(Boolean).join(", ");
  const net = byId("r-net");
  net.textContent = `${signed(db, 1)} dB ${currentMetric()}`;
  net.title = `${signed(db, 2)} dB ${currentMetric()} unrounded`;

  // The chip describes the selected value, and the note beside it says what the evidence range crosses.
  // Red and green are for values the airport would call noticeable, and need a complete figure.
  const chip = byId("r-chip");
  chip.hidden = false;
  const louder = db > 0.2;
  const quieter = db < -0.2;
  const noticeable = !noThrust && Math.abs(db) >= NOTICEABLE_DB;
  chip.textContent = louder ? "▲ Louder" : (quieter ? "▼ Quieter" : "≈ No change");
  chip.className = `chip${noticeable && louder ? " is-louder" : ""}${noticeable && quieter ? " is-quieter" : ""}`;
}

// ---------------------------------------------------------------------------
// Moving the line with the pointer and keyboard
// ---------------------------------------------------------------------------

// The distance under the pointer, or null when it's outside the plots
function distanceAtPointer(event) {
  const area = chartLayout();
  const rect = event.currentTarget.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  if (x < area.L || x > area.R || y < area.profile.top || y > area.noise.bottom) return null;
  return xToDistance(x, area);
}

function movePointer(event) {
  if (state.probePinned) return;
  const nm = distanceAtPointer(event);
  if (nm === null) return;
  state.probeNM = nm;
  redraw();
}

function rememberProbePress(event) {
  probePress = { x: event.clientX, y: event.clientY, pointerType: event.pointerType };
}

// Pins at the point clicked. Unpinning works anywhere on the canvas, and the line picks up at the pointer.
function toggleProbePin(event) {
  if (!probePress) return; // A click from an assistive tool or script can arrive with no press before it
  // Letting go after dragging across the charts is a click too, but not a request to pin
  if (Math.hypot(event.clientX - probePress.x, event.clientY - probePress.y) > CLICK_SLOP_PX) return;
  // Without hover the line already stays where it's put, so a tap only moves it. It can still unpin, on a device with both a mouse and touch.
  if (probePress.pointerType !== "mouse" && !state.probePinned) return;
  const nm = distanceAtPointer(event);
  if (nm === null && !state.probePinned) return;
  if (nm !== null) state.probeNM = nm;
  setProbePinned(!state.probePinned);
}

function setProbePinned(pinned) {
  state.probePinned = pinned;
  byId("chart").classList.toggle("is-pinned", pinned);
  redraw();
  announceProbe(pinned ? "Line pinned. " : "Line unpinned. ");
}

function moveProbeWithKeys(event) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    if (!event.repeat) setProbePinned(!state.probePinned);
    return;
  }
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  event.preventDefault();
  // RWY 09 is drawn with distance increasing to the left
  const further = (event.key === "ArrowRight") === (state.runway === "27");
  state.probeNM = event.shiftKey
    ? constrain(state.probeNM + (further ? 0.5 : -0.5), 0, CHART_MAX_NM)
    : nudgedDistance(state.probeNM, further);
  redraw();
  announceProbe();
}

// One step along the 0.05 nm grid, stopping at 0.50 km and 5.00 km when crossing them
function nudgedDistance(from, further) {
  const step = 0.05;
  const gridIndex = further
    ? Math.floor((from + NM_TOLERANCE) / step) + 1
    : Math.ceil((from - NM_TOLERANCE) / step) - 1;
  const next = constrain(gridIndex * step, 0, CHART_MAX_NM);
  const stops = usingAirportTable() ? [MIN_MODEL_NM, MAX_AIRPORT_NM] : [MIN_MODEL_NM];
  for (const stop of stops) {
    const crossing = (from < stop - NM_TOLERANCE && next > stop - NM_TOLERANCE)
      || (from > stop + NM_TOLERANCE && next < stop + NM_TOLERANCE);
    if (crossing) return stop;
  }
  return next;
}

function announceProbe(prefix = "") {
  clearTimeout(announceTimer);
  announceTimer = setTimeout(() => {
    const rangeText = byId("r-range").textContent;
    byId("probe-status").textContent = `${prefix}${byId("r-distance").textContent}: ${byId("r-net-label").textContent} ${byId("r-net").textContent}${rangeText === "—" ? "" : `, evidence range ${rangeText}`}`;
  }, 150);
}

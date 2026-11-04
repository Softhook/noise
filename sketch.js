/**
 * LCY Runway 27 Approach Slope & Acoustic Differential Model
 * Compares Current 5.5° Steep Approach vs Proposed 4.49° Shallow Approach (0 to 6.5 nm)
 * Paste directly into https://editor.p5js.org/
 */

const WAYPOINTS = [
  { nm: 0.0,  curr: 55,   propDiag: 70,   propTrue: 70,   label: "Rwy 27", loc: "Woolwich" },
  { nm: 1.0,  curr: 640,  propDiag: 574,  propTrue: 547,  label: "1nm",    loc: "Thamesmead" },
  { nm: 2.0,  curr: 1225, propDiag: 1024, propTrue: 1024, label: "2nm",    loc: "Abbey Wood / Thamesmead" },
  { nm: 3.0,  curr: 1810, propDiag: 1501, propTrue: 1501, label: "3nm",    loc: "Belvedere / Lesnes Abbey" },
  { nm: 4.0,  curr: 2395, propDiag: 1978, propTrue: 1978, label: "4nm",    loc: "River Thames / Erith" },
  { nm: 5.03, curr: 3000, propDiag: 2472, propTrue: 2472, label: "Curr TOD", loc: "Rainham Marshes" },
  { nm: 6.14, curr: 3000, propDiag: 3000, propTrue: 3000, label: "Prop TOD", loc: "Purfleet" }
];

const PRESETS = [
  {
    name: "1. Pure Geometry (Same Aircraft)",
    desc: "Isolates the 20log10(d1/d2) proximity & atmospheric effect of dropping from 5.5° to 4.49°.",
    sourceDelta: 0.0,
    thrustDelta: 0.0
  },
  {
    name: "2. Airport Claim (Optimistic A320neo vs E190)",
    desc: "Assumes A320neo is 2.5 dB quieter on approach than E190 with zero thrust penalty.",
    sourceDelta: -2.5,
    thrustDelta: 0.0
  },
  {
    name: "3. EASA Empirical (A320neo vs Legacy E190)",
    desc: "EASA TCDSN approach delta (-0.6 dB for heavier 66t airframe) + 1.2 dB thrust/config penalty.",
    sourceDelta: -0.6,
    thrustDelta: 1.2
  },
  {
    name: "4. True Future Baseline (A320neo vs E190-E2 / A220)",
    desc: "Compares A320neo (4.49°) against modern steep-certified E190-E2/A220 (5.5°). +1.6 dB louder source.",
    sourceDelta: 1.6,
    thrustDelta: 1.0
  }
];

let activePreset = 2; // Default to EASA Empirical
let sourceSlider, thrustSlider;
let useTrue1nm = false;
let metricMode = "LAmax"; // "LAmax" (20log) or "SEL" (10log)
let probeNM = 2.0;        // Default highlight at 2.0 nm

function setup() {
  createCanvas(1080, 720);
  textFont("system-ui, -apple-system, sans-serif");

  // Sliders for manual parameter exploration
  sourceSlider = createSlider(-4.0, 3.0, PRESETS[activePreset].sourceDelta, 0.1);
  sourceSlider.position(740, 65);
  sourceSlider.style("width", "140px");
  sourceSlider.input(() => { activePreset = -1; });

  thrustSlider = createSlider(0.0, 2.5, PRESETS[activePreset].thrustDelta, 0.1);
  thrustSlider.position(910, 65);
  thrustSlider.style("width", "140px");
  thrustSlider.input(() => { activePreset = -1; });
}

function applyPreset(idx) {
  activePreset = idx;
  sourceSlider.value(PRESETS[idx].sourceDelta);
  thrustSlider.value(PRESETS[idx].thrustDelta);
}

// Interpolate altitudes at any distance x (in nm)
function getAltitudes(nm) {
  nm = constrain(nm, 0.1, 6.5);
  if (nm >= 6.14) return { curr: 3000, prop: 3000 };

  for (let i = 0; i < WAYPOINTS.length - 1; i++) {
    let w1 = WAYPOINTS[i];
    let w2 = WAYPOINTS[i + 1];
    if (nm >= w1.nm && nm <= w2.nm) {
      let t = (nm - w1.nm) / (w2.nm - w1.nm);
      let cAlt = lerp(w1.curr, w2.curr, t);
      let p1 = useTrue1nm ? w1.propTrue : w1.propDiag;
      let p2 = useTrue1nm ? w2.propTrue : w2.propDiag;
      let pAlt = lerp(p1, p2, t);
      return { curr: cAlt, prop: pAlt };
    }
  }
  return { curr: 3000, prop: 3000 };
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

  // Operational thrust penalty applies when descending on the 4.49° glide slope (0 to 6.14 nm)
  let sDelta = sourceSlider.value();
  let tDelta = (nm < 6.14) ? thrustSlider.value() : 0.0;

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

function draw() {
  background(15, 19, 28);

  // Layout bounds
  const L = 75, R = width - 45;
  const topY1 = 135, botY1 = 385; // Flight profile panel
  const topY2 = 435, botY2 = 635; // Noise delta panel

  // Update interactive probe if mouse is inside chart area
  if (mouseX >= L && mouseX <= R && mouseY >= topY1 && mouseY <= botY2) {
    // Runway is on Left (L), 6.5 nm is on Right (R)
    probeNM = constrain(map(mouseX, L, R, 0.0, 6.5), 0.2, 6.5);
  }

  drawHeader();
  drawFlightProfile(L, R, topY1, botY1);
  drawNoiseGraph(L, R, topY2, botY2);
  drawProbeReadout(L, R, topY1, botY2);
}

function drawHeader() {
  noStroke();
  fill(24, 30, 44);
  rect(0, 0, width, 115);

  fill(240, 245, 255);
  textSize(16);
  textStyle(BOLD);
  text("LCY Runway 27 Approach: Altitude & Ground Noise Differential Model", 20, 26);

  textSize(12);
  textStyle(NORMAL);
  fill(160, 175, 200);
  let descText = activePreset >= 0 ? PRESETS[activePreset].desc : "Custom manual slider configuration.";
  text(descText, 20, 46);

  // Preset buttons
  for (let i = 0; i < PRESETS.length; i++) {
    let bx = 20 + i * 172;
    let by = 58, bw = 165, bh = 28;
    let isAct = (activePreset === i);
    fill(isAct ? color(56, 130, 246) : color(38, 46, 66));
    stroke(isAct ? color(120, 180, 255) : color(65, 78, 105));
    rect(bx, by, bw, bh, 5);

    noStroke();
    fill(isAct ? 255 : 200);
    textSize(10.5);
    textAlign(CENTER, CENTER);
    text(PRESETS[i].name, bx + bw / 2, by + bh / 2);
  }

  // Toggle buttons for Metric (LAmax vs SEL) & 1nm Typo Correction
  let mBtnX = 20, mBtnY = 91;
  fill(45, 55, 78);
  stroke(90, 105, 135);
  rect(mBtnX, mBtnY, 210, 20, 4);
  noStroke();
  fill(220);
  textSize(10.5);
  text(`Metric: ${metricMode === "LAmax" ? "Peak LAmax (20 log)" : "Exposure SEL (10 log)"} [Click]`, mBtnX + 105, mBtnY + 10);

  let tBtnX = 240;
  fill(useTrue1nm ? color(140, 65, 90) : color(45, 55, 78));
  stroke(110, 125, 155);
  rect(tBtnX, mBtnY, 265, 20, 4);
  noStroke();
  fill(235);
  text(`1nm Alt: ${useTrue1nm ? "True 4.49° Math (547 ft)" : "Diagram Label '574 ft' (Typo)"} [Click]`, tBtnX + 132, mBtnY + 10);

  textAlign(LEFT, BASELINE);
  fill(210, 220, 240);
  textSize(11);
  text(`Source Δ: ${nf(sourceSlider.value(), 1, 1)} dB`, 740, 56);
  text(`4.49° Thrust Δ: +${nf(thrustSlider.value(), 1, 1)} dB`, 910, 56);
  fill(140, 155, 180);
  textSize(10);
  text("(Aircraft Base vs Baseline)", 740, 100);
  text("(Shallow Slope Drag/Spool)", 910, 100);
}

function drawFlightProfile(L, R, topY, botY) {
  // Panel background
  fill(20, 26, 38);
  stroke(45, 55, 75);
  rect(L, topY, R - L, botY - topY, 4);

  // Horizontal altitude grid lines
  textAlign(RIGHT, CENTER);
  textSize(10);
  for (let alt = 0; alt <= 3500; alt += 500) {
    let y = map(alt, 0, 3400, botY, topY);
    stroke(35, 44, 62);
    line(L, y, R, y);
    noStroke();
    fill(130, 145, 170);
    text(alt + " ft", L - 8, y);
  }

  // Shaded altitude wedge between Current (5.5°) and Proposed (4.49°)
  noStroke();
  fill(236, 72, 153, 42);
  beginShape();
  for (let nm = 0; nm <= 6.5; nm += 0.05) {
    let x = map(nm, 0, 6.5, L, R);
    let y = map(getAltitudes(nm).curr, 0, 3400, botY, topY);
    vertex(x, y);
  }
  for (let nm = 6.5; nm >= 0; nm -= 0.05) {
    let x = map(nm, 0, 6.5, L, R);
    let y = map(getAltitudes(nm).prop, 0, 3400, botY, topY);
    vertex(x, y);
  }
  endShape(CLOSE);

  // Draw Current 5.5° Slope (Purple)
  noFill();
  stroke(168, 85, 247);
  strokeWeight(2.8);
  beginShape();
  for (let nm = 0; nm <= 6.5; nm += 0.05) {
    vertex(map(nm, 0, 6.5, L, R), map(getAltitudes(nm).curr, 0, 3400, botY, topY));
  }
  endShape();

  // Draw Proposed 4.49° Slope (Pink)
  stroke(244, 114, 182);
  strokeWeight(2.8);
  beginShape();
  for (let nm = 0; nm <= 6.5; nm += 0.05) {
    vertex(map(nm, 0, 6.5, L, R), map(getAltitudes(nm).prop, 0, 3400, botY, topY));
  }
  endShape();
  strokeWeight(1);

  // Waypoint markers & Community Labels
  for (let w of WAYPOINTS) {
    let x = map(w.nm, 0, 6.5, L, R);
    let yc = map(w.curr, 0, 3400, botY, topY);
    let pAlt = useTrue1nm ? w.propTrue : w.propDiag;
    let yp = map(pAlt, 0, 3400, botY, topY);

    stroke(55, 68, 95, 150);
    line(x, yc, x, botY);

    fill(168, 85, 247);
    noStroke();
    circle(x, yc, 7);
    fill(244, 114, 182);
    circle(x, yp, 7);

    if (w.nm > 0) {
      textSize(10);
      textAlign(CENTER, BOTTOM);
      fill(205, 165, 255);
      text(`${w.curr}ft`, x, yc - 6);

      textAlign(CENTER, TOP);
      fill(255, 175, 215);
      if (w.nm < 6.0) text(`${pAlt}ft`, x, yp + 6);
    }

    // Ground location boxes
    fill(32, 40, 58);
    stroke(75, 90, 120);
    rectMode(CENTER);
    rect(x, botY + 14, textWidth(w.loc) + 10, 16, 3);
    rectMode(CORNER);
    noStroke();
    fill(200, 215, 235);
    textSize(9.5);
    textAlign(CENTER, CENTER);
    text(w.loc, x, botY + 14);
  }

  // Panel title & legend
  textAlign(LEFT, TOP);
  fill(220, 230, 245);
  textStyle(BOLD);
  textSize(12);
  text("VERTICAL FLIGHT PROFILE (Runway 27 Final Approach from East)", L + 12, topY + 10);
  textStyle(NORMAL);
  fill(168, 85, 247);
  text("● Current 5.5° Steep Slope (3,000ft TOD @ 5.03 nm)", L + 12, topY + 28);
  fill(244, 114, 182);
  text("● Proposed 4.49° Shallow Slope (3,000ft TOD @ 6.14 nm)", L + 12, topY + 44);
}

function drawNoiseGraph(L, R, topY, botY) {
  fill(20, 26, 38);
  stroke(45, 55, 75);
  rect(L, topY, R - L, botY - topY, 4);

  // dB Y-axis scale (-3 dB to +6 dB)
  const minDB = -3.0, maxDB = 6.0;
  let zeroY = map(0, minDB, maxDB, botY, topY);

  textAlign(RIGHT, CENTER);
  textSize(10);
  for (let db = -3; db <= 6; db += 1) {
    let y = map(db, minDB, maxDB, botY, topY);
    stroke(db === 0 ? color(130, 145, 175) : color(35, 44, 62));
    strokeWeight(db === 0 ? 1.5 : 1);
    line(L, y, R, y);
    noStroke();
    fill(db > 0 ? color(255, 140, 140) : (db < 0 ? color(120, 230, 170) : 220));
    text((db > 0 ? "+" : "") + db + " dB", L - 8, y);
  }

  // +3 dB double acoustic energy reference line
  let y3 = map(3.0, minDB, maxDB, botY, topY);
  stroke(255, 90, 90, 110);
  drawingContext.setLineDash([4, 4]);
  line(L, y3, R, y3);
  drawingContext.setLineDash([]);
  noStroke();
  fill(255, 120, 120, 190);
  textAlign(RIGHT, BOTTOM);
  textSize(9.5);
  text("+3 dB (Double Acoustic Energy / Clearly Perceptible Threshold)", R - 10, y3 - 3);

  // Dashed curve: Pure Geometric + Atmospheric Penalty alone
  noFill();
  stroke(56, 189, 248, 180);
  strokeWeight(1.8);
  drawingContext.setLineDash([5, 4]);
  beginShape();
  for (let nm = 0.2; nm <= 6.5; nm += 0.05) {
    let ac = getAcoustics(nm);
    let x = map(nm, 0, 6.5, L, R);
    let y = map(constrain(ac.geomDB + ac.atmDB, minDB, maxDB), minDB, maxDB, botY, topY);
    vertex(x, y);
  }
  endShape();
  drawingContext.setLineDash([]);

  // Shaded fill under Net Noise Difference curve
  noStroke();
  fill(245, 158, 11, 45);
  beginShape();
  vertex(map(0.2, 0, 6.5, L, R), zeroY);
  for (let nm = 0.2; nm <= 6.5; nm += 0.05) {
    let ac = getAcoustics(nm);
    let x = map(nm, 0, 6.5, L, R);
    let y = map(constrain(ac.netDB, minDB, maxDB), minDB, maxDB, botY, topY);
    vertex(x, y);
  }
  vertex(map(6.5, 0, 6.5, L, R), zeroY);
  endShape(CLOSE);

  // Solid curve: Total Net Ground Noise Change
  noFill();
  stroke(251, 191, 36);
  strokeWeight(3);
  beginShape();
  for (let nm = 0.2; nm <= 6.5; nm += 0.05) {
    let ac = getAcoustics(nm);
    let x = map(nm, 0, 6.5, L, R);
    let y = map(constrain(ac.netDB, minDB, maxDB), minDB, maxDB, botY, topY);
    vertex(x, y);
  }
  endShape();
  strokeWeight(1);

  // Distance X-axis labels
  textAlign(CENTER, TOP);
  fill(160, 175, 200);
  textSize(10.5);
  for (let nm = 0; nm <= 6; nm++) {
    let x = map(nm, 0, 6.5, L, R);
    stroke(60, 75, 100);
    line(x, botY, x, botY + 5);
    noStroke();
    text(nm + " nm", x, botY + 8);
  }

  textAlign(LEFT, TOP);
  fill(220, 230, 245);
  textStyle(BOLD);
  textSize(12);
  text(`GROUND NOISE DIFFERENTIAL (Δ ${metricMode}: Louder > 0 dB | Quieter < 0 dB)`, L + 12, topY + 10);
  textStyle(NORMAL);
  fill(251, 191, 36);
  text("━ Total Net Ground Noise Impact (Altitude + Atmosphere + Source + Thrust)", L + 12, topY + 26);
  fill(56, 189, 248);
  text("┅ Pure Altitude Proximity & Atmospheric Penalty Alone", L + 440, topY + 26);
}

function drawProbeReadout(L, R, topY1, botY2) {
  let x = map(probeNM, 0, 6.5, L, R);
  let ac = getAcoustics(probeNM);

  // Vertical interactive crosshair
  stroke(255, 255, 255, 140);
  strokeWeight(1.2);
  line(x, topY1, x, botY2);

  // Highlight dots on profile and noise curves
  let yc = map(ac.currAlt, 0, 3400, 385, topY1);
  let yp = map(ac.propAlt, 0, 3400, 385, topY1);
  let yn = map(constrain(ac.netDB, -3, 6), -3, 6, botY2, 435);

  fill(255);
  circle(x, yc, 8);
  circle(x, yp, 8);
  fill(251, 191, 36);
  circle(x, yn, 10);

  // Bottom HUD bar showing exact math breakdown at probeNM
  fill(26, 34, 50);
  stroke(75, 95, 130);
  rect(L, 665, R - L, 44, 6);

  noStroke();
  fill(255);
  textAlign(LEFT, CENTER);
  textSize(12);
  textStyle(BOLD);
  text(`PROBE @ ${nf(probeNM, 1, 2)} nm:`, L + 15, 687);

  textStyle(NORMAL);
  textSize(11.5);
  fill(200, 215, 240);
  text(`5.5° Alt: ${round(ac.currAlt)} ft  |  4.49° Alt: ${round(ac.propAlt)} ft  (Drop: -${round(ac.deltaFt)} ft)`, L + 135, 687);

  fill(56, 189, 248);
  text(`Dist+Atm: +${nf(ac.geomDB + ac.atmDB, 1, 2)} dB`, L + 455, 687);

  fill(190, 205, 230);
  text(`Source+Thrust: ${ac.sourceDB + ac.thrustDB >= 0 ? "+" : ""}${nf(ac.sourceDB + ac.thrustDB, 1, 2)} dB`, L + 605, 687);

  let netCol = ac.netDB > 0.2 ? color(255, 115, 115) : (ac.netDB < -0.2 ? color(110, 235, 165) : color(250, 205, 80));
  fill(netCol);
  textStyle(BOLD);
  textSize(13);
  text(`NET GROUND Δ: ${ac.netDB >= 0 ? "+" : ""}${nf(ac.netDB, 1, 2)} dB`, L + 790, 687);
  textStyle(NORMAL);
}

function mousePressed() {
  // Check preset buttons
  for (let i = 0; i < PRESETS.length; i++) {
    let bx = 20 + i * 172, by = 58, bw = 165, bh = 28;
    if (mouseX >= bx && mouseX <= bx + bw && mouseY >= by && mouseY <= by + bh) {
      applyPreset(i);
      return;
    }
  }
  // Metric toggle button
  if (mouseX >= 20 && mouseX <= 230 && mouseY >= 91 && mouseY <= 111) {
    metricMode = (metricMode === "LAmax") ? "SEL" : "LAmax";
  }
  // 1nm Typo toggle button
  if (mouseX >= 240 && mouseX <= 505 && mouseY >= 91 && mouseY <= 111) {
    useTrue1nm = !useTrue1nm;
  }
}
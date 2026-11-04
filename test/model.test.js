const test = require("node:test");
const assert = require("node:assert/strict");
const model = require("../model.js");

const near = (actual, expected, tolerance, message) => {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${message || "value"}: ${actual} is not within ${tolerance} of ${expected}`);
};
const RUNWAYS = ["27", "09"];

test("altitudes follow the published slopes", () => {
  const feetPerNm = 6076.12;
  for (const runway of RUNWAYS) {
    for (const nm of [1, 2, 3]) {
      const { curr, prop } = model.altitudes(runway, nm);
      near(curr, 55 + Math.tan((5.5 * Math.PI) / 180) * feetPerNm * nm, 2, "5.5° slope");
      near(prop, 70 + Math.tan((4.49 * Math.PI) / 180) * feetPerNm * nm, 2, "4.49° slope");
    }
  }
});

test("altitudes reach the threshold heights and stay level beyond the descent", () => {
  for (const runway of RUNWAYS) {
    assert.deepEqual(model.altitudes(runway, 0), { curr: 55, prop: 70 });
    const last = model.WAYPOINTS[runway].at(-1);
    assert.deepEqual(model.altitudes(runway, 6.5), { curr: last.curr, prop: last.prop });
  }
});

test("SEL uses 10 log and LAmax uses 20 log", () => {
  const air = ((1225 - 1024) / 1000) * 0.6;
  near(model.altitudeAndAirDB("27", 2, "SEL"), 10 * Math.log10(1225 / 1024) + air, 1e-9);
  near(model.altitudeAndAirDB("27", 2, "LAmax"), 20 * Math.log10(1225 / 1024) + air, 1e-9);
});

test("airport tables have ten figures per aircraft and match spot values from Figs. 17-18", () => {
  for (const runway of RUNWAYS) {
    for (const aircraft of model.AIRCRAFT) {
      assert.equal(model.ARRIVALS[runway][aircraft].length, model.ARRIVAL_KM.length);
    }
  }
  assert.equal(model.ARRIVALS["27"]["E190"][9], -1.0);
  assert.equal(model.ARRIVALS["09"]["E190"][9], -0.9);
  assert.equal(model.ARRIVALS["27"]["A220"][9], -4.0);
  assert.equal(model.ARRIVALS["09"]["A220"][4], -1.7);
  assert.equal(model.ARRIVALS["27"]["E190-E2"][9], -1.9);
  assert.equal(model.ARRIVALS["09"]["E195-E2"][4], -0.9);
});

test("E190 and A220 differ by 3.0 dB everywhere, as both use 737-500 data at +1.5 and −1.5 dB", () => {
  for (const runway of RUNWAYS) {
    model.ARRIVAL_KM.forEach((km, i) => {
      near(model.ARRIVALS[runway]["E190"][i] - model.ARRIVALS[runway]["A220"][i], 3.0, 1e-9, `RWY ${runway} at ${km} km`);
    });
  }
});

test("airportDifference flips the sign, interpolates, and returns null outside the table", () => {
  const nmAt = km => km / model.KM_PER_NM;
  near(model.airportDifference("27", "E190", nmAt(0.5)), -2.2, 1e-9);
  near(model.airportDifference("27", "A220", nmAt(5)), 4.0, 1e-9);
  near(model.airportDifference("27", "E190", nmAt(1.25)), -1.6, 1e-9);
  assert.equal(model.airportDifference("27", "E190", nmAt(0.4)), null);
  assert.equal(model.airportDifference("27", "E190", nmAt(5.1)), null);
});

test("the A320neo is louder than every other aircraft except the E190 at all ten points", () => {
  for (const runway of RUNWAYS) {
    for (const aircraft of ["E190-E2", "E195-E2", "A220"]) {
      assert.ok(model.ARRIVALS[runway][aircraft].every(value => value < 0), `${aircraft} on RWY ${runway}`);
    }
  }
});

test("thrust adds noise while both descend, reverses in the gap, and is zero when both are level", () => {
  for (const runway of RUNWAYS) {
    const points = model.WAYPOINTS[runway];
    const current = points.at(-2).nm;
    const proposed = points.at(-1).nm;
    assert.equal(model.thrustTermDB(runway, 1, 1.2), 1.2);
    assert.equal(model.thrustTermDB(runway, (current + proposed) / 2, 1.2), -2.0);
    assert.equal(model.thrustTermDB(runway, proposed + 0.2, 1.2), 0);
  }
});

test("the reversal scales with the slider below the Fig. 22 cap, and no thrust effect stays at zero", () => {
  near(model.thrustTermDB("27", 5.6, 0.2), -0.2 * 4.46, 0.01);
  assert.equal(model.thrustTermDB("27", 1, 0), 0);
  assert.equal(model.thrustTermDB("27", 5.6, 0), 0);
  assert.equal(model.thrustTermDB("27", 6.5, 0), 0);
});

test("thrust changes gradually, with no step between neighbouring distances", () => {
  for (const runway of RUNWAYS) {
    for (let nm = 0; nm < 6.5; nm += 0.01) {
      const change = Math.abs(model.thrustTermDB(runway, nm + 0.01, 1.2) - model.thrustTermDB(runway, nm, 1.2));
      assert.ok(change < 0.12, `RWY ${runway} at ${nm.toFixed(2)} nm changes by ${change}`);
    }
  }
});

test("the net figure is the sum of its parts", () => {
  const result = model.acoustics("27", 2, { metric: "LAmax", sourceDB: -0.6, thrustDB: 1.2 });
  near(result.netDB, result.geometryDB - 0.6 + 1.2, 1e-9);
  near(result.netDB, 2.28, 0.01);
  assert.equal(result.deltaFt, 201);
});

test("the evidence range contains the model and spans the published bands", () => {
  const options = { metric: "LAmax", sourceRange: [-2.0, 1.1], thrustRange: [0, 2.5] };
  const range = model.evidenceRange("27", 2, options);
  near(range.low, -0.32, 0.01);
  near(range.high, 5.28, 0.01);

  const gap = model.evidenceRange("27", 5.6, options);
  const gapGeometry = model.altitudeAndAirDB("27", 5.6, "LAmax");
  near(gap.low, gapGeometry - 2.0 - 2.0, 1e-9, "thrust reversal lowers the gap's low end");
  near(gap.high, gapGeometry + 1.1, 1e-9);
});

test("the fitted E190-E2 source sits inside its certificate range", () => {
  for (const runway of RUNWAYS) {
    const fit = model.fittedSourceDB(runway, "E190-E2");
    const [low, high] = model.SOURCE_RANGES["E190-E2"].range;
    assert.ok(fit >= low && fit <= high, `RWY ${runway}: ${fit}`);
  }
});

test("the fitted model stays within 0.6 dB of the E190-E2 column", () => {
  for (const runway of RUNWAYS) {
    const fit = model.fittedSourceDB(runway, "E190-E2");
    model.ARRIVAL_KM.forEach((km, i) => {
      const nm = km / model.KM_PER_NM;
      const predicted = model.acoustics(runway, nm, { metric: "SEL", sourceDB: fit, thrustDB: 0 }).netDB;
      near(predicted, -model.ARRIVALS[runway]["E190-E2"][i], 0.6, `RWY ${runway} at ${km} km`);
    });
  }
});

test("flight forecasts add up to the two runway columns in Fig. 3", () => {
  assert.equal(model.FLIGHTS_WITHOUT_CHANGE["E190"][2027], 11712 + 24888);
  assert.equal(model.FLIGHTS_WITHOUT_CHANGE["E190"][2038], 1248 + 2652);
  assert.equal(model.FLIGHTS_WITHOUT_CHANGE["E190-E2"][2027], 448 + 952);
  assert.equal(model.FLIGHTS_WITHOUT_CHANGE["E190-E2"][2038], 1248 + 2652);
  assert.equal(model.FLIGHTS_WITHOUT_CHANGE["E195-E2"][2027], 512 + 1088);
  assert.equal(model.FLIGHTS_WITHOUT_CHANGE["E195-E2"][2038], 21440 + 45560);
  assert.equal(model.FLIGHTS_WITHOUT_CHANGE["A220"][2027], 2240 + 4760);
  assert.equal(model.FLIGHTS_WITHOUT_CHANGE["A220"][2038], 6432 + 13668);
});

/**
 * Checks on the notes and scenario values that the page itself can't report when they go wrong.
 * Run from the project folder with: node --test tests/
 */

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.join(__dirname, "..");

// The scripts share one global scope, as they do in the page. Only these two p5 functions are needed outside drawing.
const page = vm.createContext({
  constrain: (value, low, high) => Math.min(Math.max(value, low), high),
  lerp: (from, to, t) => from + (to - from) * t
});
for (const file of ["data", "model", "citations", "scenarios"]) {
  vm.runInContext(fs.readFileSync(path.join(ROOT, "js", `${file}.js`), "utf8"), page);
}
const inPage = code => vm.runInContext(code, page);

const SCENARIOS = inPage("SCENARIOS");
const state = inPage("state");
const citationParts = inPage("citationParts");
const METRICS = ["LAmax", "SEL"];

// Runs check once for every scenario, runway and metric that can be selected
function forEachSelection(check) {
  SCENARIOS.forEach((scenario, index) => {
    for (const runway of scenario.site ? ["27"] : ["27", "09"]) {
      for (const metric of METRICS) {
        state.scenarioIndex = index;
        state.runway = runway;
        state.metric = metric;
        state.sourceDelta = scenario.sourceDelta ?? 0;
        state.thrustDelta = scenario.thrustDelta ?? 0;
        check(scenario);
      }
    }
  });
}

function allNotes() {
  const notes = new Set();
  forEachSelection(scenario => {
    for (const note of [scenario.desc(), ...scenario.sources()]) notes.add(note);
    if (!scenario.usesAirportTable) {
      for (const note of inPage("heightAndAirSources()")) notes.add(note);
    }
  });
  return [...notes];
}

// Every linked page in the notes, with the note text that comes before it
function allPageLinks() {
  const links = [];
  for (const note of allNotes()) {
    let before = "";
    for (const part of citationParts(note)) {
      if (part.doc && part.page !== undefined) links.push({ ...part, before, note });
      before += part.text;
    }
  }
  return links;
}

function sliderStep(id) {
  const html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
  const tag = html.match(new RegExp(`<input[^>]*id="${id}"[^>]*>`))[0];
  return Number(tag.match(/step="([^"]+)"/)[1]);
}

test("every cited document is in the Documents folder", () => {
  for (const { file } of inPage("CITED_DOCUMENTS")) {
    assert.ok(fs.existsSync(path.join(ROOT, "Documents", file)), `Missing ${file}`);
  }
});

// Checked against the PDFs. Keyed by each document's number in the Documents folder.
test("each type's certificate note links to its own certificate pages", () => {
  const expected = {
    "E190": [["10", 46]],
    "E190-E2": [["10", 190]],
    "E195-E2": [["10", 194]],
    "A220": [["18", 3]],
    "Dash 8-Q400": [["27", 48], ["27", 50]]
  };
  for (const [aircraft, pages] of Object.entries(expected)) {
    const scenario = SCENARIOS.find(entry => entry.name === `EASA: ${aircraft}`);
    const note = scenario.sources().find(line => line.startsWith("**Where the certificates are.**"));
    const links = Array.from(citationParts(note))
      .filter(part => part.doc && part.page !== undefined)
      .map(part => [part.doc.file.slice(0, 2), part.page]);
    assert.deepStrictEqual(links, [["09", 175], ["09", 226], ...pages], aircraft);
  }
});

test("every linked page is within its document", () => {
  for (const { text, doc, note } of allPageLinks()) {
    const lastPage = Number(text.match(/\d+$/)[0]);
    assert.ok(lastPage <= doc.pages, `"${text}" is past the end of ${doc.file} (${doc.pages} pages) in: ${note}`);
  }
});

// A page takes the document last named, so a page after a source that isn't listed would link to the wrong one.
// So a page must follow a listed name, open a bracket, or carry on from an earlier page with "and".
test("every linked page follows a listed document", () => {
  const names = inPage("CITED_DOCUMENTS").map(entry => entry.name.source).join("|");
  const allowed = new RegExp(`(?:(?:${names})(?: report| Appendix \\w+)?,? |\\(|(?:\\bp\\.\\d+|\\)) and )$`);
  for (const { text, before, note } of allPageLinks()) {
    if (/^\d/.test(text)) continue; // A later number in a list such as pp.50, 61
    assert.ok(allowed.test(before), `"${text}" doesn't follow a listed document in: ${note}`);
  }
});

// An EASA sheet missing from CITED_DOCUMENTS would send its pages to the sheet named before it
test("every EASA sheet in the notes is a known document", () => {
  const names = inPage("CITED_DOCUMENTS").map(entry => entry.name);
  for (const note of allNotes()) {
    for (const [sheet] of note.matchAll(/EASA [\w -]+? sheet/g)) {
      assert.ok(names.some(name => name.test(sheet)), `Unknown document "${sheet}" in: ${note}`);
    }
  }
});

// A page takes the document last named, so a page in a later sentence could quietly link to the wrong one
test("every linked page has its document named in the same sentence", () => {
  const sentenceEnd = /[.!?]\*{0,2}\)? +\*{0,2}[A-Z]/;
  for (const note of allNotes()) {
    let sinceName = null;
    for (const part of citationParts(note)) {
      if (!part.doc || part.page === undefined) {
        const naming = inPage("CITED_DOCUMENTS").some(entry => new RegExp(`^(?:${entry.name.source})$`).test(part.text));
        sinceName = naming ? "" : sinceName === null ? null : sinceName + part.text;
        continue;
      }
      assert.ok(!sentenceEnd.test(sinceName ?? ""), `"${part.text}" is a sentence away from its document in: ${note}`);
      sinceName += part.text;
    }
  }
});

// A slider snaps to its step and range, so a value that doesn't fit would differ from the value charted
test("every scenario's values fit the sliders, in both metrics", () => {
  const sliders = [
    { key: "sourceDelta", range: inPage("SOURCE_SLIDER"), step: sliderStep("source-slider") },
    { key: "thrustDelta", range: inPage("THRUST_SLIDER"), step: sliderStep("thrust-slider") }
  ];
  forEachSelection(scenario => {
    if (scenario.usesAirportTable) return;
    for (const { key, range, step } of sliders) {
      const value = scenario[key];
      const steps = (value - range.min) / step;
      const label = `${scenario.name} ${key} ${value} (${state.metric})`;
      assert.ok(value >= range.min && value <= range.max, `${label} is outside the slider`);
      assert.ok(Math.abs(steps - Math.round(steps)) < 1e-6, `${label} isn't on a slider step`);
    }
  });
});

// The shaded range is meant to contain the scenario's own line at every distance it is drawn
test("every scenario's line stays inside its evidence range", () => {
  forEachSelection(scenario => {
    if (scenario.usesAirportTable) return;
    const start = inPage("MIN_MODEL_NM");
    for (let nm = start; nm <= inPage("CHART_MAX_NM"); nm += 0.01) {
      const { netDB } = page.getAcoustics(nm);
      const { low, high } = page.evidenceRangeAt(nm);
      const label = `${scenario.name}, RWY ${state.runway}, ${state.metric}, ${nm.toFixed(2)} nm`;
      assert.ok(netDB >= low - 1e-6 && netDB <= high + 1e-6, `${label}: ${netDB} is outside ${low} to ${high}`);
    }
  });
});

// Only while both aircraft descend does the band include 5.5° thrust relief
test("the thrust band follows the flight phase", () => {
  const thrust = [-0.45, 2.5];
  for (const runway of ["27", "09"]) {
    state.runway = runway;
    const currTOD = page.currentTopOfDescent().nm;
    const propTOD = page.proposedTopOfDescent().nm;
    assert.deepStrictEqual([...page.thrustRangeAt(currTOD, thrust)], thrust);
    assert.deepStrictEqual([...page.thrustRangeAt(currTOD + 0.01, thrust)], [-2, 0]);
    assert.deepStrictEqual([...page.thrustRangeAt(propTOD, thrust)], [-0.45, 0.45]);
  }
});

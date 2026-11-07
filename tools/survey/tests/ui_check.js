// Runs the survey app's own scripts (survey/ui/) without a browser, so their logic can be tested.
//     node tests/ui_check.js survey/ui/index.html < case.json
// The scripts are run together, in the order index.html loads them.
// The page's DOM calls go to do-nothing stand-ins, and its first fetch fails, so it stops before
// drawing anything. case.json gives a day's data ({data, receptor, sources}); this prints which
// event each pass was given, and the sources in the page's order. case.json's sources are also
// the ones switched on. If case.json gives a measure, it also prints the "By aircraft type" rows for
// it, over every flight: [type, passes, [[source, values, median]]].
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const page = process.argv[2];
const html = fs.readFileSync(page, "utf8");
const script = [...html.matchAll(/<script src="([^"]+)"><\/script>/g)]
  .map((m) => fs.readFileSync(path.join(path.dirname(page), m[1]), "utf8")).join("\n");

function stand_in() {
  const store = {};
  return new Proxy(function () {}, {
    get(target, key) {
      if (key in store) return store[key];
      if (key === "then") return undefined;  // Not a promise
      if (key === Symbol.toPrimitive) return () => "";
      return stand_in();
    },
    set(target, key, value) { store[key] = value; return true; },
    apply() { return stand_in(); },
  });
}

const context = {
  document: stand_in(), window: stand_in(), CSS: { escape: (s) => s }, DOMPoint: function () {},
  fetch: () => Promise.reject(new Error("no server")), requestAnimationFrame: () => 0, console,
};
vm.createContext(context);
vm.runInContext(`${script}\n;globalThis.__ui = { state, matchedEvents, bySource, typeRows };`, context);
const ui = context.__ui;

const input = JSON.parse(fs.readFileSync(0, "utf8"));
ui.state.data = input.data;
ui.state.sources = new Set(input.sources);  // The sources switched on
const owner = ui.matchedEvents(input.receptor);
ui.state.eventOf = owner;
process.stdout.write(JSON.stringify({
  events: Object.fromEntries([...owner].map(([pass, e]) => [pass, e.lmax_db])),
  order: input.sources.slice().sort(ui.bySource),
  types: input.measure ? ui.typeRows(input.data.flights, input.measure, input.receptor).map((r) =>
    [r.type, r.passes, r.lanes.map((l) => [l.source, l.dots.map((d) => d.v), l.median])]) : null,
}));

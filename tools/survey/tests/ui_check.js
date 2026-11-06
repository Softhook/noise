// Runs the survey app's own script (survey/ui.html) without a browser, so its logic can be tested.
//     node tests/ui_check.js survey/ui.html < case.json
// The page's DOM calls go to do-nothing stand-ins, and its first fetch fails, so it stops before
// drawing anything. case.json gives a day's data ({data, receptor, sources}); this prints which
// event each pass was given, and the sources in the page's order.
"use strict";
const fs = require("fs");
const vm = require("vm");

const html = fs.readFileSync(process.argv[2], "utf8");
const script = html.slice(html.indexOf("<script>") + "<script>".length, html.lastIndexOf("</script>"));

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
vm.runInContext(`${script}\n;globalThis.__ui = { state, assignEvents, bySource };`, context);
const ui = context.__ui;

const input = JSON.parse(fs.readFileSync(0, "utf8"));
ui.state.data = input.data;
const owner = ui.assignEvents(input.receptor);
process.stdout.write(JSON.stringify({
  events: Object.fromEntries([...owner].map(([pass, e]) => [pass, e.lmax_db])),
  order: input.sources.slice().sort(ui.bySource),
}));

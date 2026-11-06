// The passes table, the selected pass's detail, and selecting a pass from any view.
"use strict";

// Each noise event at the receptor goes to at most one pass: of the passes whose closest approach
// came from 5 s before its LAmax to 40 s before it (sound takes a few seconds to arrive, and the
// clocks may differ a little), the one that came closest to the receptor. Each pass then shows the
// loudest event it was given. It isn't a match (ARCHITECTURE.md, Match, is still to be built), but
// two passes never both claim one event. Worked out over every pass of the day, whatever the
// filters, so filtering never moves an event to another pass.
const EVENT_BEFORE_S = 5, EVENT_AFTER_S = 40;
function assignEvents(r) {
  const passes = new Map();
  for (const f of state.data.flights) {
    const a = f.approaches[r];
    const p = passes.get(f.pass_id) || { t: Infinity, ground: Infinity };
    p.t = Math.min(p.t, a ? toT(a.t) : toT(f.first_utc));
    if (a && a.ground_m !== null) p.ground = Math.min(p.ground, a.ground_m);
    passes.set(f.pass_id, p);
  }
  const list = [...passes.entries()].sort((a, b) => a[1].t - b[1].t);
  const owner = new Map();
  for (const e of state.data.events) {
    if (e.receptor !== r) continue;
    const at = toT(e.lmax_utc);
    let best = null;
    for (const [id, p] of list) {
      const dt = at - p.t;
      if (dt < -EVENT_BEFORE_S || dt > EVENT_AFTER_S) continue;
      if (!best || p.ground < best[1].ground || (p.ground === best[1].ground && p.t < best[1].t)) best = [id, p];
    }
    if (!best) continue;
    const had = owner.get(best[0]);
    if (!had || Number(e.lmax_db) > Number(had.lmax_db)) owner.set(best[0], e);
  }
  return owner;
}
const eventNear = (passId) => state.eventOf.get(passId) || null;
function drawTable(passes) {
  const r = $("f-receptor").value, sources = state.data.sources.filter((s) => state.sources.has(s));
  // Δ height compares the first two sources shown, in source order
  const pair = sources.length >= 2 ? sources.slice(0, 2) : null;
  const top = (name, num, cls) => h("th", { rowspan: 2, class: [num ? "num" : "", cls || ""].join(" ").trim() }, name);
  const row1 = [top("Closest (UTC)", false, "pin"), top("Registration", false, "pin pin2"), top("Callsign"), top("Type")];
  const row2 = [];
  for (const s of sources) {
    row1.push(h("th", { colspan: 2, class: "group" }, key(s, colourOf(s), isRadar(s)), " ", sourceName(s)));
    row2.push(h("th", { class: "num", text: "m away" }), h("th", { class: "num", text: "m up" }));
  }
  if (pair) row1.push(h("th", { rowspan: 2, class: "num", title: "Height at closest approach, the first source's minus the second's. Left out where either is at its track's end." },
    "Δ height (m)", h("div", { class: "sub-th", text: `${sourceName(pair[0])} − ${sourceName(pair[1])}` })));
  row1.push(h("th", { rowspan: 2, class: "num", title: `The loudest noise event at the receptor whose LAmax came ${EVENT_BEFORE_S} s before to ${EVENT_AFTER_S} s after this pass's closest approach, unless another pass in that time came closer to the receptor. A guide, not a match.` }, "LAmax (dB)"));
  const thead = $("table").querySelector("thead");
  thead.replaceChildren(h("tr", {}, ...row1), h("tr", {}, ...row2));
  const rows = passes.map((p) => {
    const by = Object.fromEntries(p.flights.map((f) => [f.source, f]));
    const reg = p.flights.map((f) => f.registration).find(Boolean) || "";
    const call = p.flights.map((f) => f.callsign).find(Boolean) || "";
    const type = p.flights.map((f) => f.type).find(Boolean) || "";
    const cells = [h("td", { class: "pin", text: hms(p.t) }), h("td", { class: "pin pin2", text: reg || "–" }), h("td", { text: call || "–" }), h("td", { text: type || "–" })];
    const unseen = unseenOf(p.id);
    for (const s of sources) {
      if (!by[s] && unseen[s]) {
        cells.push(h("td", { colspan: 2, class: "why" + (unseen[s] === "unexplained" ? " unexplained" : ""),
          title: unseen[s] === "unexplained" ? `${sourceName(s)} had data then, and the aircraft was in its area and below its ceiling, but it has no flight here` : `${sourceName(s)} couldn't have seen it: ${unseen[s]}`,
          text: WHY[unseen[s]] || unseen[s] }));
        continue;
      }
      const a = by[s] && by[s].approaches[r];
      const cls = "num" + (a && a.at_track_end ? " end" : "");
      cells.push(h("td", { class: cls, text: a ? fmt(a.ground_m, 0) : "" }), h("td", { class: cls, text: a ? fmt(a.height_m, 0) : "" }));
    }
    if (pair) {
      const [a, b] = pair.map((s) => by[s] && by[s].approaches[r]);
      const ok = a && b && !a.at_track_end && !b.at_track_end && a.height_m !== null && b.height_m !== null;
      const diff = ok ? a.height_m - b.height_m : null;
      cells.push(h("td", { class: "num", text: ok ? (diff >= 0 ? "+" : "") + fmt(diff, 0) : "" }));
    }
    const ev = eventNear(p.id);
    cells.push(h("td", { class: "num", text: ev ? fmt(Number(ev.lmax_db), 1) : "" }));
    const tr = h("tr", { class: p.id === state.selected ? "selected" : "", tabindex: 0, "data-pass": p.id, "aria-selected": String(p.id === state.selected) }, ...cells);
    tr.addEventListener("click", () => select(p.id, "table"));
    tr.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(p.id, "table"); }
      else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const next = e.key === "ArrowDown" ? tr.nextElementSibling : tr.previousElementSibling;
        if (next) next.focus();
      }
    });
    return tr;
  });
  $("table").querySelector("tbody").replaceChildren(...rows);
  $("table").style.setProperty("--col1", thead.rows[0].cells[0].offsetWidth + "px");
  $("table").style.setProperty("--head1", thead.rows[0].cells[4] ? thead.rows[0].cells[4].offsetHeight + "px" : "29px");
  $("table-count").textContent = `${passes.length} passes`;
}
function drawDetail(passes) {
  const box = $("detail");
  const fs = state.data.flights.filter((f) => f.pass_id === state.selected);
  if (!fs.length) { box.className = "empty"; box.textContent = "Click a track, tick or row."; return; }
  box.className = "";
  const r = $("f-receptor").value;
  const parts = passes.some((p) => p.id === state.selected) ? [] : [h("p", { class: "hidden-note", text: "Not in the table or map now: the filters, sources or time window leave it out." })];
  parts.push(h("dl", {}, h("dt", { text: "Pass" }), h("dd", { text: state.selected }),
    h("dt", { text: "Linked by" }), h("dd", { text: fs.length > 1 ? (fs.map((f) => f.evidence).find(Boolean) || "not recorded") : "only one source" })));
  for (const f of fs.sort((a, b) => bySource(a.source, b.source))) {
    const a = f.approaches[r] || {};
    parts.push(h("div", { class: "detail-source" }, key(f.source, colourOf(f.source), isRadar(f.source)), sourceName(f.source)));
    const rows = [["Registration", f.registration], ["Callsign", f.callsign], ["Type", f.type], ["Hex", f.hex], ["Squawk", f.squawk],
      ["Direction", { A: "Arrival", D: "Departure", O: "Other" }[f.direction] || f.direction], ["From / to", [f.origin, f.destination].filter(Boolean).join(" → ")],
      ["Seen", `${hms(toT(f.first_utc))}–${hms(toT(f.last_utc))}`], ["Closest at", a.t ? hms(toT(a.t)) : ""],
      ["Ground distance (m)", fmt(a.ground_m, 0)], ["Height (m above sea level)", fmt(a.height_m, 0)], ["Slant (m)", fmt(a.slant_m, 0)],
      ["Note", a.at_track_end ? "closest point is at the end of this source's track" : ""]];
    parts.push(h("dl", {}, ...rows.filter(([, v]) => v && v !== "–").flatMap(([k, v]) => [h("dt", { text: k }), h("dd", { text: String(v) })])));
  }
  for (const [s, why] of Object.entries(unseenOf(state.selected))) {
    parts.push(h("div", { class: "detail-source" }, key(s, colourOf(s), isRadar(s)), `Not in ${sourceName(s)}`));
    parts.push(h("p", { class: "note" + (why === "unexplained" ? " unexplained" : ""), text: why === "unexplained"
      ? "It should have seen this pass: it had data then, and the aircraft was in its area and below its ceiling for at least 20 s. Either its data has a gap, or the pass wasn't linked."
      : `It couldn't have seen this pass: ${why === "no data" ? "it has no data for that time" : why === "outside its area" ? "the aircraft never came into the area it covers" : "the aircraft stayed above its ceiling while in its area"}.` }));
  }
  box.replaceChildren(...parts);
}
// The passes table scrolls both ways: by its scrollbars, by dragging it with the mouse, and sideways
// with Shift and the wheel. A drag doesn't also select the row it started on.
function scrollableTable() {
  const wrap = document.querySelector(".table-wrap");
  let drag = null, dragged = false;
  wrap.addEventListener("pointerdown", (e) => {
    if (e.pointerType !== "mouse" || e.button !== 0) return;
    drag = { x: e.clientX, y: e.clientY, left: wrap.scrollLeft, top: wrap.scrollTop, id: e.pointerId };
    dragged = false;
  });
  wrap.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!dragged) {
      if (Math.hypot(dx, dy) < 5) return;
      dragged = true;
      wrap.setPointerCapture(e.pointerId);
      wrap.classList.add("dragging");
      window.getSelection().removeAllRanges();
    }
    wrap.scrollLeft = drag.left - dx;
    wrap.scrollTop = drag.top - dy;
  });
  const end = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    drag = null;
    wrap.classList.remove("dragging");
    if (wrap.hasPointerCapture(e.pointerId)) wrap.releasePointerCapture(e.pointerId);
  };
  wrap.addEventListener("pointerup", end);
  wrap.addEventListener("pointercancel", end);
  wrap.addEventListener("click", (e) => { if (dragged) { e.stopPropagation(); e.preventDefault(); dragged = false; } }, true);
  wrap.addEventListener("wheel", (e) => {
    if (!e.shiftKey || e.deltaX || wrap.scrollWidth <= wrap.clientWidth) return;
    e.preventDefault();
    wrap.scrollLeft += e.deltaMode === 1 ? e.deltaY * 16 : e.deltaMode === 2 ? e.deltaY * wrap.clientWidth : e.deltaY;
  }, { passive: false });
}
// from: "map", "timeline" or "table". The selected pass is brought into view in the others.
function select(id, from) {
  state.selected = state.selected === id ? null : id;
  render();
  if (!state.selected) return;
  if (from !== "map") revealOnPlan();
  if (from !== "table") {
    const row = $("table").querySelector(`tr[data-pass="${CSS.escape(state.selected)}"]`);
    if (row) {
      const wrap = row.closest(".table-wrap"), head = $("table").querySelector("thead").offsetHeight;
      if (row.offsetTop < wrap.scrollTop + head || row.offsetTop + row.offsetHeight > wrap.scrollTop + wrap.clientHeight) {
        wrap.scrollTop = row.offsetTop - head - (wrap.clientHeight - head) / 2;
      }
    }
  }
}
// Pan the map, keeping its zoom, if the selected pass's closest approach is out of view.
function revealOnPlan() {
  const r = $("f-receptor").value, v = planView();
  for (const f of state.data.flights.filter((f2) => f2.pass_id === state.selected && state.sources.has(f2.source))) {
    const a = f.approaches[r], pts = local[trackKey(f)];
    if (!a || !pts || !pts.length) continue;
    const t = toT(a.t), p = pts.reduce((b, q) => (Math.abs(q[0] - t) < Math.abs(b[0] - t) ? q : b));
    if (Math.abs(p[1] - v.cx) > v.half * 0.9 || Math.abs(p[2] - v.cy) > v.half * 0.9) {
      state.view.plan = { cx: p[1], cy: p[2], half: v.half };
      redraw("plan");
    }
    return;
  }
}

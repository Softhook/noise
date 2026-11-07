// The page: drawing it all, choosing the deployment and day, and starting up. Loaded last.
"use strict";

function tiles(flights, passes) {
  const d = state.data, r = $("f-receptor").value;
  const several = passes.filter((p) => new Set(p.flights.map((f) => f.source)).size > 1).length;
  const missed = passes.filter((p) => unexplained(p.id)).length;
  // Events follow the receptor, the time window and the source switches, but not the search or the
  // pass filters, so the count includes events matched to no pass
  const events = d.events.filter((e) => e.receptor === r && state.sources.has(e.source) &&
    (!state.window || (toT(e.lmax_utc) >= state.window[0] && toT(e.lmax_utc) <= state.window[1])));
  const items = [["Passes", passes.length], ["In several sources", several], ["Missed, unexplained", missed],
    ["Noise events", events.length], ["Events not matched", events.filter((e) => !e.pass_id).length]];
  $("tiles").replaceChildren(...items.map(([l, v]) => h("div", { class: "tile" }, h("div", { class: "label", text: l }), h("div", { class: "value", text: v.toLocaleString("en-GB") }))));
}
function render() {
  if (!state.data) return;
  const flights = shownFlights(), passes = passesOf(flights);
  state.eventOf = matchedEvents($("f-receptor").value);
  drawTimeline(shownFlights(null));
  drawPlan(flights);
  drawProfile(flights);
  drawTypes(flights);
  drawTable(passes);
  drawDetail(passes);
  tiles(flights, passes);
  for (const node of document.querySelectorAll("[data-receptor]")) node.textContent = receptor().label;
}

function deployment() { return state.deployments.find((d) => d.deployment === $("f-deployment").value); }
function fillDays() {
  const d = deployment();
  const sel = $("f-day"), prev = sel.value;
  sel.replaceChildren(...(d && d.days || []).map((day) => {
    const covered = Object.entries(day.minutes).map(([s, m]) => `${sourceName(s)} ${m >= 1440 ? "all day" : (m / 60).toFixed(1) + " h"}`).join(", ");
    return h("option", { value: day.day, text: `${day.day}${covered ? " · " + covered : ""}` });
  }));
  if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
  $("subtitle").textContent = !d ? "No deployments." : d.error ? `Can't read ${d.deployment}'s manifest: ${d.error}` : (d.description || d.deployment);
  $("built").textContent = d && d.built ? `Built ${d.built_utc.replace("T", " ").slice(0, 16)} UTC` : d && d.error ? "" : d && d.outdated ? "Needs a rebuild" : "Not built yet";
  $("rebuild").disabled = !!(d && d.error);
  $("warnings").replaceChildren(...(d && d.warnings || []).map((w) => h("li", {}, h("span", { class: "icon", "aria-hidden": "true", text: "!" }), h("span", { text: w }))));
}
async function loadDay() {
  const d = deployment();
  if (!d || !d.built || !$("f-day").value) {
    state.data = null;
    $("content").hidden = true;
    if (d && !d.built && !d.error) $("subtitle").textContent = `${d.deployment} ${d.outdated ? "was built by an older version of the survey" : "isn't built yet"}. Press Rebuild, or run: make build DEPLOYMENT=${d.deployment}`;
    return;
  }
  $("content").hidden = false;
  $("content").classList.add("loading");
  try {
    const data = await api(`/api/day?deployment=${encodeURIComponent(d.deployment)}&day=${encodeURIComponent($("f-day").value)}`);
    state.data = data;
    state.window = null;
    state.selected = null;
    state.view = { plan: null, profile: null, timeline: null };
    indexLevels();
    state.radar = new Set(data.flights.filter((f) => f.height_kind === "radar").map((f) => f.source));
    const recSel = $("f-receptor"), prev = recSel.value;
    recSel.replaceChildren(...data.receptors.map((r) => h("option", { value: r.id, text: r.public ? `${r.label} (${r.lat.toFixed(5)}, ${r.lon.toFixed(5)})` : r.label })));
    if (data.receptors.some((r) => r.id === prev)) recSel.value = prev;
    const box = $("f-sources");
    // Sources start on; one switched off stays off from day to day
    state.sources = new Set(data.sources.filter((s) => !state.off.has(s)));
    box.replaceChildren(...data.sources.map((s) => {
      const input = h("input", { type: "checkbox" });
      input.checked = state.sources.has(s);
      input.addEventListener("change", () => {
        if (input.checked) { state.sources.add(s); state.off.delete(s); } else { state.sources.delete(s); state.off.add(s); }
        render();
      });
      return h("label", { class: "chip" }, input, key(s, colourOf(s), isRadar(s)), sourceName(s));
    }));
    projectTracks();
    render();
  } catch (error) {
    $("subtitle").textContent = `Couldn't load the day: ${error.message}`;
  } finally {
    $("content").classList.remove("loading");
  }
}
async function loadDeployments(keep) {
  state.deployments = await api("/api/deployments");
  const sel = $("f-deployment"), prev = keep || sel.value;
  sel.replaceChildren(...state.deployments.map((d) => h("option", { value: d.deployment, text: d.deployment + (d.error ? " (can't read)" : d.built ? "" : d.outdated ? " (needs a rebuild)" : " (not built)") })));
  // The newest deployment first, unless one was already chosen
  if (prev && state.deployments.some((d) => d.deployment === prev)) sel.value = prev;
  else if (state.deployments.length) sel.value = state.deployments[state.deployments.length - 1].deployment;
  fillDays();
}
async function start() {
  try {
    await loadDeployments();
  } catch (error) {
    $("subtitle").textContent = `Couldn't reach the survey app: ${error.message}`;
    return;
  }
  $("f-deployment").addEventListener("change", async () => { fillDays(); await loadDay(); });
  $("f-day").addEventListener("change", loadDay);
  $("f-receptor").addEventListener("change", () => { state.view.plan = state.view.profile = null; projectTracks(); render(); });
  for (const id of ["f-linked", "f-unexplained", "f-search", "f-within", "f-below"]) $(id).addEventListener("input", render);
  $("rebuild").addEventListener("click", async () => {
    const d = deployment();
    if (!d) return;
    $("rebuild").disabled = true;
    $("rebuild").textContent = "Rebuilding…";
    try {
      // The build runs in the background (it may analyse logs for minutes); follow it until it ends
      let job = await api("/api/build", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ deployment: d.deployment }) });
      while (job.running) {
        if (job.log.length) $("subtitle").textContent = `Rebuilding: ${job.log[job.log.length - 1]}`;
        await new Promise((resolve) => setTimeout(resolve, 1000));
        job = await api(`/api/build?deployment=${encodeURIComponent(d.deployment)}`);
      }
      if (job.error) throw new Error(job.error);
      await loadDeployments(d.deployment);
      await loadDay();
    } catch (error) {
      $("subtitle").textContent = `Rebuild failed: ${error.message}`;
    } finally {
      $("rebuild").disabled = false;
      $("rebuild").textContent = "Rebuild";
    }
  });
  scrollableTable();
  makeZoomable("plan");
  makeZoomable("profile");
  setupTimeline();
  setupTypes();
  await loadDay();
}
start();

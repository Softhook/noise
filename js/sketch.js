/**
 * London City approach noise model
 * Compares today's most common aircraft, the E190 on the 5.5° approach, with the A320neo,
 * new to the airport, on the proposed 4.49° approach (0 to 6.5 nm from the threshold).
 *
 * The scripts load in order from index.html and share one global scope, so the page still works
 * opened directly from disk:
 *   data.js       sourced figures
 *   model.js      the viewer's choices and the acoustic model
 *   citations.js  links from note text to the documents
 *   scenarios.js  the scenarios and their wording
 *   charts.js     the p5 drawing
 *   controls.js   the page's controls and readout
 *   sketch.js     p5's entry points
 */

// p5's sketch checker fetches the scripts, which browsers block when the page is opened from disk
p5.disableFriendlyErrors = true;

function setup() {
  setupSidebarResizer(); // First, so the chart starts at its final size
  const chartBox = byId("chart");
  const canvas = createCanvas(chartBox.clientWidth, chartBox.clientHeight);
  canvas.parent(chartBox);
  textFont(FONT_STACK);
  noLoop(); // The charts only change when a control or the pointer does

  setupControls();
  setupCanvas(canvas, chartBox);
  applyScenario(state.scenarioIndex);
}

function draw() {
  drawCharts();
  updateReadout();
}

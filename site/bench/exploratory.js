"use strict";
/* NONQUALIFYING PX roster: only receipt-bound per-case rows show measurements. */
const BenchExploratory = (() => {
  const SCHEMA = "ivanka.assembler-bench.exploratory-candidates.v1";
  const STATUS = {source: "Source pinned", image: "Image attested",
    pilot: "Pilot verified", benchmark: "Benchmark verified"};
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[c]);
  const short = (value) => typeof value === "string" && value.length > 14
    ? value.slice(0, 12) + "…" : (value || "—");
  const num = (value) => typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("en", {maximumFractionDigits: 2}) : "—";
  const status = (entry) => STATUS[entry.status] || entry.status;
  function resultLabel(entry) {
    const samples = Array.isArray(entry.samples) ? entry.samples.length : 0;
    if (entry.results_status === "no-image")
      return "No image built · no benchmark run · no metrics";
    if (entry.results_status === "image-only")
      return "Image receipt verified · no pilot or benchmark cases";
    if (entry.results_status === "no-per-sample-results")
      return "Run receipt verified · no per-sample results supplied";
    if (!entry.results_status.startsWith("verified-"))
      return "Unverified state · no metrics";
    const cohort = (entry.results?.cohorts || []).join(" + ");
    return samples + " verified cases (" + cohort + ") · nonqualifying";
  }
  function sampleTable(entry) {
    if (!entry.results_status.startsWith("verified-")) return "";
    const rows = (entry.samples || []).map((sample) =>
      "<tr><td>" + esc(sample.alias) + "</td><td>" +
      esc(sample.alias[3] === "R" ? "Physical" : "Synthetic") + "</td><td>" +
      esc(sample.outcome) + "</td><td>" + num(sample.score) + "</td><td>" +
      num(sample.seconds) + "</td><td>" +
      esc(sample.failure_reason || "") + "</td></tr>").join("");
    return '<details class="px-cases"><summary>Show verified per-case rows</summary>' +
      '<div class="table-scroll"><table class="exploratory-cases"><thead><tr>' +
      "<th>Case</th><th>Cohort</th><th>Outcome</th><th>Alignment</th>" +
      "<th>Runtime (s)</th><th>Failure</th></tr></thead><tbody>" + rows +
      "</tbody></table></div></details>";
  }
  function render(data, mount, context) {
    if (!data || data.schema !== SCHEMA || !Array.isArray(data.candidates)) {
      mount.textContent = "Experimental roster unavailable.";
      if (context) context.textContent = "";
      return;
    }
    const entries = data.candidates;
    const built = entries.filter((e) => e.image_sha256).length;
    const measured = entries.filter((e) =>
      e.results_status.startsWith("verified-")).length;
    if (context) context.textContent = (data.note || "") + " " +
      entries.length + " candidates · " + built + " image digests recorded · " +
      measured + " with receipt-verified cases · 0 qualifying.";
    const rows = entries.map((entry) => {
      const pins = "source " + esc(short(entry.source_commit)) +
        " · adapter " + esc(short(entry.adapter_commit));
      const image = entry.image_sha256
        ? '<span title="' + esc(entry.image_sha256) + '">' +
          esc(short(entry.image_sha256)) + "</span>"
        : "Not built";
      return "<tr><td class='cell-title'>" + esc(entry.name) + "</td><td>" +
        pins + "</td><td>" + esc(status(entry)) + "</td><td>" + image +
        "</td><td>" + esc(resultLabel(entry)) + "</td></tr>" +
        (sampleTable(entry) ? "<tr class='px-case-row'><td colspan='5'>" +
          sampleTable(entry) + "</td></tr>" : "");
    }).join("");
    mount.innerHTML = '<div class="table-scroll"><table class="exploratory-table">' +
      "<thead><tr><th>Program</th><th>Source / adapter pin</th><th>Status</th>" +
      "<th>Image digest</th><th>Per-sample evidence</th></tr></thead><tbody>" +
      rows + "</tbody></table></div>";
  }
  return {render, status, resultLabel};
})();
if (typeof module !== "undefined") module.exports = BenchExploratory;

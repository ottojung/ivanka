"use strict";
/* NONQUALIFYING PX roster: only receipt-bound per-case rows show measurements. */
const BenchExploratory = (() => {
  const SCHEMA = "ivanka.assembler-bench.exploratory-candidates.v1";
  const STATUS = {source: "Source pinned (pending)", image: "Image attested",
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
      return "Pending: No image built · no benchmark run · no metrics";
    if (entry.results_status === "image-only")
      return "Image receipt verified · pending pilot/benchmark cases";
    if (entry.results_status === "no-per-sample-results")
      return "Run receipt verified · pending per-sample results";
    if (!entry.results_status.startsWith("verified-"))
      return "Unverified state · pending metrics";
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
  function comparable(entries) {
    return entries.filter((e) => e.results_status.startsWith("verified-")
      && Array.isArray(e.samples) && e.samples.length);
  }
  function caseIndex(entry) {
    const map = new Map();
    for (const sample of entry.samples || []) map.set(sample.alias, sample);
    return map;
  }
  function delta(a, b) {
    return (typeof a === "number" && typeof b === "number"
      && Number.isFinite(a) && Number.isFinite(b)) ? a - b : null;
  }
  function compareTable(entries, aId, bId) {
    const a = entries.find((e) => e.id === aId);
    const b = entries.find((e) => e.id === bId);
    if (!a || !b || a.id === b.id) {
      return '<p class="subtle px-compare-hint">Select two different candidates with verified per-case rows for a nonqualifying side-by-side comparison.</p>';
    }
    const aMap = caseIndex(a), bMap = caseIndex(b);
    const aliases = [...new Set([...aMap.keys(), ...bMap.keys()])].sort();
    if (!aliases.length) {
      return '<p class="subtle px-compare-hint">No verified per-case rows available for this comparison.</p>';
    }
    const rows = aliases.map((alias) => {
      const sa = aMap.get(alias), sb = bMap.get(alias);
      const dScore = delta(sa?.score, sb?.score);
      const dSec = delta(sa?.seconds, sb?.seconds);
      return "<tr><td>" + esc(alias) + "</td><td>" +
        esc(alias[3] === "R" ? "Physical" : "Synthetic") + "</td><td>" +
        esc(sa?.outcome || "—") + "</td><td>" + num(sa?.score) + "</td><td>" +
        num(sa?.seconds) + "</td><td>" +
        esc(sb?.outcome || "—") + "</td><td>" + num(sb?.score) + "</td><td>" +
        num(sb?.seconds) + "</td><td>" + num(dScore) + "</td><td>" +
        num(dSec) + "</td></tr>";
    }).join("");
    return '<div class="table-scroll"><table class="exploratory-cases px-compare-table">' +
      "<caption>Nonqualifying side-by-side comparison: " + esc(a.name) +
      " vs " + esc(b.name) + ". Δ is A − B on reported values only; missing values stay missing.</caption>" +
      "<thead><tr><th>Case</th><th>Cohort</th><th>" + esc(a.name) + " outcome</th><th>" +
      esc(a.name) + " align</th><th>" + esc(a.name) + " s</th><th>" +
      esc(b.name) + " outcome</th><th>" + esc(b.name) + " align</th><th>" +
      esc(b.name) + " s</th><th>Δ align</th><th>Δ s</th></tr></thead><tbody>" +
      rows + "</tbody></table></div>";
  }
  function compareControls(entries, aId, bId) {
    const options = comparable(entries);
    const opt = (selected) => '<option value="">Select candidate…</option>' +
      options.map((e) => '<option value="' + esc(e.id) + '"' +
        (e.id === selected ? " selected" : "") + ">" + esc(e.name) +
        "</option>").join("");
    const note = options.length < 2
      ? '<p class="subtle px-compare-hint">Side-by-side comparison becomes available when at least two candidates have receipt-verified per-case rows. No qualifying metrics, gates, or Ψ matrices are affected.</p>'
      : '<p class="subtle px-compare-hint">Side-by-side comparison uses only receipt-verified per-case rows. It is nonqualifying and does not change original seven qualifying metrics, gates, or Ψ matrices.</p>';
    return '<div class="px-compare-controls" aria-label="PX side-by-side comparison">' +
      '<label>COMPARE A <select id="pxCompareA">' + opt(aId) + "</select></label>" +
      '<label>COMPARE B <select id="pxCompareB">' + opt(bId) + "</select></label>" +
      "</div>" + note;
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
    const q = typeof mount.querySelector === "function"
      ? (sel) => mount.querySelector(sel) : () => null;
    const prevA = q("#pxCompareA")?.value || "";
    const prevB = q("#pxCompareB")?.value || "";
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
      rows + "</tbody></table></div>" +
      '<div class="px-compare" id="pxCompare">' +
      compareControls(entries, prevA, prevB) +
      '<div id="pxCompareResult">' + compareTable(entries, prevA, prevB) + "</div></div>";
    const rerenderCompare = () => {
      const aId = q("#pxCompareA")?.value || "";
      const bId = q("#pxCompareB")?.value || "";
      const target = q("#pxCompareResult");
      if (target) target.innerHTML = compareTable(entries, aId, bId);
    };
    const on = (sel, ev, fn) => { const n = q(sel); if (n?.addEventListener) n.addEventListener(ev, fn); };
    on("#pxCompareA", "change", rerenderCompare);
    on("#pxCompareB", "change", rerenderCompare);
  }
  return {render, status, resultLabel, compareTable};
})();
if (typeof module !== "undefined") module.exports = BenchExploratory;

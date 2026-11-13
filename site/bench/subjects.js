"use strict";
/* Shared pure interpretation: never compute Ψ from cohort averages or a
   single-case mapping snapshot. Only verified per-sample proofs count. */
const BenchSubjects = (() => {
  function criterion(report, a, b, subject, direction) {
    const key = subject === "alignment" || subject === "runtime"
      ? subject : "diagnostic:" + subject + ":" + direction;
    if (subject !== "alignment" && subject !== "runtime" &&
        direction === "unspecified") {
      return {status:"unresolved", paired:0, expected:report.expected_samples,
        proof:null, reason:"No beneficial direction was chosen"};
    }
    const entry = report.metrics?.[key]?.[a]?.[b];
    if (entry) return entry;
    return {status:"incomplete", paired:0, expected:report.expected_samples,
      proof:null, reason:"No independently proven full-cohort Ψ for this metric"};
  }
  function conjunction(entries) {
    if (!entries.length) return "none";
    const statuses = entries.map(x => x.status);
    if (statuses.every(x => x === "self")) return "self";
    // A demonstrated counterexample falsifies a conjunction even if other
    // subjects are unavailable. Unknown cannot prove a positive verdict.
    if (statuses.includes("does-not-dominate")) return "does-not-dominate";
    if (statuses.includes("incomplete")) return "incomplete";
    if (statuses.includes("unresolved")) return "unresolved";
    return statuses.every(x => x === "dominates") ? "dominates" : "unresolved";
  }
  function evaluate(report, a, b, selected) {
    const entries = selected.map(({key,direction,label}) => ({
      key,label,direction, ...criterion(report,a,b,key,direction)
    }));
    return {status:conjunction(entries), entries};
  }
  return {criterion,conjunction,evaluate};
})();
if (typeof module !== "undefined") module.exports = BenchSubjects;

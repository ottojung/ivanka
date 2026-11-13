"use strict";
/* Shared pure interpretation: never compute Ψ from cohort averages or a
   single-case mapping snapshot. Only verified per-sample proofs count. */
const BenchSubjects = (() => {
  function criterion(report, a, b, subject, direction, snapshot) {
    const key = subject === "alignment" || subject === "runtime"
      ? subject : "diagnostic:" + subject + ":" + direction;
    if (subject !== "alignment" && subject !== "runtime" &&
        direction === "unspecified") {
      return {status:"unresolved", paired:0, expected:report.expected_samples,
        proof:null, reason:"No beneficial direction was chosen"};
    }
    const entry = report.metrics?.[key]?.[a]?.[b];
    if (entry) return entry;
    const v1 = snapshot?.tools?.[a]?.values?.[subject];
    const v2 = snapshot?.tools?.[b]?.values?.[subject];
    const available = subject !== "alignment" && subject !== "runtime" &&
      snapshot?.status === "INCOMPLETE" &&
      Number.isFinite(v1) && Number.isFinite(v2);
    const delta=available ? (direction==="lower" ? v2-v1 : v1-v2) : null;
    return {status:"incomplete",paired:available ? snapshot.cases_measured : 0,
      expected:report.expected_samples,proof:null,
      observed:available?{gains:Number(delta>0),losses:Number(delta<0),
        ties:Number(delta===0),mean_delta:delta}:null,
      reason:available ? "Observed diagnostic snapshot only; no full-cohort Ψ proof"
        : "No paired measurements available for this subject"};
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
  function verdict(status) {
    // A cell answers ONLY "does row A dominate column B on the entire
    // selected set of subjects?" Descriptive gains are never the answer.
    const states = {
      "dominates": {label:"YES", explanation:"Certified strict all-r Ψ dominance"},
      "does-not-dominate": {label:"NO",
        explanation:"At least one selected subject disproves strict Ψ dominance"},
      "incomplete": {label:"?", explanation:"Insufficient complete paired data"},
      "unresolved": {label:"?", explanation:"Numerical proof unresolved"},
      "self": {label:"—", explanation:"Same assembler"},
      "none": {label:"?", explanation:"Select at least one subject"}
    };
    return states[status]||{label:"?",explanation:"Dominance cannot be verified"};
  }
  function evaluate(report, a, b, selected, snapshot) {
    const entries = selected.map(({key,direction,label}) => ({
      key,label,direction, ...criterion(report,a,b,key,direction,snapshot)
    }));
    return {status:conjunction(entries), entries};
  }
  return {criterion,conjunction,evaluate,verdict};
})();
if (typeof module !== "undefined") module.exports = BenchSubjects;

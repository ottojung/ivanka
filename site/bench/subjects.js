"use strict";
/* Interpret independent all-r paired-subset proofs separately from full-
   cohort certification. A one-case source-validated diagnostic has an exact
   sign proof; no averaged score is ever misrepresented as signed-power Ψ. */
const BenchSubjects = (() => {
  function pairedDiagnostics(run,snapshot,subject,direction,a,b,expected) {
    if(!run || typeof BenchRanks==="undefined" || !run.samples?.length)
      return null;
    const one=new Map(BenchRanks.measurements(run,snapshot,subject,a)
      .map(x=>[x.id,x.value]));
    const two=new Map(BenchRanks.measurements(run,snapshot,subject,b)
      .map(x=>[x.id,x.value]));
    const differences=[...one].flatMap(([id,v])=>
      two.has(id)?[direction==="lower"?two.get(id)-v:v-two.get(id)]:[]);
    const n=differences.length;
    if(!n)return null;
    const gains=differences.filter(v=>v>0).length;
    const losses=differences.filter(v=>v<0).length;
    const ties=n-gains-losses;
    const psi0=(gains-losses)/n;
    const psi1=differences.reduce((sum,v)=>sum+v,0)/n;
    const psi2=differences.reduce((sum,v)=>sum+v*Math.abs(v),0)/n;
    const positive=losses===0 && gains>0;
    const refuted=gains===0 || psi0<=0 || psi1<=0 || psi2<=0;
    const status=positive?"dominates":
      refuted?"does-not-dominate":"unresolved";
    return {
      status:"incomplete",paired:n,expected,proof:null,
      observed:{gains,losses,ties,mean_delta:psi1},
      subset:{status,proof:{
        kind:"observed-paired-signed-powers",sample_count:n,
        psi0,psi1,psi2,
        ...(positive?{sign:1}:refuted?{sign:-1}:{})}},
      reason:positive?"All measured differences are nonnegative, some positive":
        refuted?"Observed paired-subset Ψ has a nonpositive witness":
        "Observed mixed differences need a strict all-r proof",
    };
  }

  function criterion(report, a, b, subject, direction, snapshot, run) {
    const key = subject === "alignment" || subject === "runtime"
      ? subject : "diagnostic:" + subject + ":" + direction;
    if (subject !== "alignment" && subject !== "runtime" &&
        direction === "unspecified") {
      return {status:"unresolved", paired:0, expected:report.expected_samples,
        proof:null, reason:"No beneficial direction was chosen"};
    }
    // Core proofs are published in their canonical directions. Reversing
    // the preference is exactly equivalent to exchanging the two arms.
    const flipped=(subject==="alignment"&&direction==="lower")||
      (subject==="runtime"&&direction==="higher");
    const entry = flipped?report.metrics?.[key]?.[b]?.[a]:
      report.metrics?.[key]?.[a]?.[b];
    if (entry) return entry;
    if(subject!=="alignment" && subject!=="runtime") {
      const paired=pairedDiagnostics(
        run,snapshot,subject,direction,a,b,report.expected_samples);
      if(paired)return paired;
    }
    const v1 = snapshot?.tools?.[a]?.values?.[subject];
    const v2 = snapshot?.tools?.[b]?.values?.[subject];
    const available = subject !== "alignment" && subject !== "runtime" &&
      snapshot?.status === "INCOMPLETE" &&
      snapshot?.cases_measured === 1 &&
      typeof snapshot?.sample_alias === "string" &&
      Number.isFinite(v1) && Number.isFinite(v2);
    const delta=available ? (direction==="lower" ? v2-v1 : v1-v2) : null;
    return {status:"incomplete",paired:available ? snapshot.cases_measured : 0,
      expected:report.expected_samples,proof:null,
      observed:available?{gains:Number(delta>0),losses:Number(delta<0),
        ties:Number(delta===0),mean_delta:delta}:null,
      subset:available?{
        status:delta>0?"dominates":"does-not-dominate",
        proof:{kind:"exact-single-observation",sample_count:1,
          sign:Math.sign(delta)}}:
        {status:"no-data",proof:null},
      reason:available ? "Exact signed-power result for one observed diagnostic case"
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
      "dominates": {label:"YES", explanation:"Strict all-r Ψ dominance across the full cohort"},
      "does-not-dominate": {label:"NO",
        explanation:"At least one selected subject disproves strict Ψ dominance"},
      "incomplete": {label:"?", explanation:"Insufficient complete paired data"},
      "unresolved": {label:"?", explanation:"Numerical proof unresolved"},
      "self": {label:"—", explanation:"Same assembler"},
      "none": {label:"?", explanation:"Select at least one subject"}
    };
    return states[status]||{label:"?",explanation:"Dominance cannot be verified"};
  }
  function observedVerdict(result) {
    // The top label answers the dominance question for the observations
    // available NOW, rather than suppressing a computed result with '?'.
    // A full-cohort proof remains a separate, stronger claim.
    if (["dominates","does-not-dominate","self"].includes(result.status)) {
      const full=verdict(result.status);
      return {...full, kind:"full-yes", scope:"Entire measured cohort"};
    }
    const statuses=result.entries.map(item=>{
      if (["dominates","does-not-dominate","unresolved"].includes(item.status))
        return item.status;
      return item.subset?.status||"no-data";
    });
    const measured=statuses.filter(x=>x==="dominates"||
      x==="does-not-dominate").length;
    const total=statuses.length;
    const completeness=measured+"/"+total+" selected subjects measured";
    if (statuses.includes("does-not-dominate"))
      return {label:"NO",kind:"observed-no",
        explanation:"Strict Ψ does not dominate on the observed paired subset of at least one selected subject",
        scope:completeness};
    if (statuses.includes("unresolved")||statuses.includes("unresolved-direction"))
      return {label:"—",kind:"unresolved",
        explanation:"Observed-subset all-r Ψ proof remains unresolved",
        scope:completeness};
    if (measured===total&&total>0)
      return {label:"YES",kind:"observed-yes",
        explanation:"Strict Ψ dominates on the observed paired subset of every selected subject; full cohort is not certified",
        scope:completeness};
    if (measured>0)
      return {label:"YES",kind:"partial-yes",
        explanation:"Dominates on observed paired subsets, but other selected subjects have no measurements",
        scope:completeness};
    return {label:"—",kind:"no-data",
      explanation:"No paired observations available for the selected subjects",
      scope:completeness};
  }
  function evidence(result, limit=2) {
    // An observation is deliberately NOT a dominance verdict. Surface the
    // actual within-subject paired wins/losses and coverage in each matrix
    // cell, without upgrading incomplete data to a proof.
    const observed = result.entries.flatMap(item => {
      const o=item.observed;
      if (!o || !Number.isInteger(item.paired) || item.paired<=0 ||
          !Number.isInteger(item.expected) || item.expected<item.paired ||
          ![o.gains,o.losses,o.ties].every(Number.isInteger) ||
          o.gains<0 || o.losses<0 || o.ties<0 ||
          o.gains+o.losses+o.ties!==item.paired) return [];
      const text=o.gains+"↑ "+o.losses+"↓ "+o.ties+"= · "+
        item.paired+"/"+item.expected;
      return [{key:item.key,label:item.label,paired:item.paired,
        expected:item.expected,gains:o.gains,losses:o.losses,
        ties:o.ties,text}];
    });
    const cap=Math.max(1,Number.isInteger(limit)?limit:2);
    return {rows:observed.slice(0,cap),
      additional:Math.max(0,observed.length-cap),
      observedSubjects:observed.length,
      selectedSubjects:result.entries.length,
      description:observed.map(item=>item.label+": "+item.text).join("; ")};
  }
  function tailSign(differences) {
    const counts=new Map();
    for(const d of differences) {
      if(!Number.isFinite(d))return null;
      if(d!==0)counts.set(Math.abs(d),(counts.get(Math.abs(d))||0)+Math.sign(d));
    }
    for(const magnitude of [...counts.keys()].sort((a,b)=>b-a)) {
      if(counts.get(magnitude))return Math.sign(counts.get(magnitude));
    }
    return 0;
  }
  function infinitySign(entry, context) {
    const proof=entry.proof||entry.subset?.proof;
    const limit=proof?.psi_at_positive_infinity;
    if(limit==="+inf")return 1;
    if(limit==="-inf")return -1;
    if(typeof limit==="number" && limit!==0 && Number.isFinite(limit))
      return Math.sign(limit);
    const counts=entry.observed;
    if(counts && counts.gains+counts.losses+counts.ties===entry.paired) {
      if(counts.losses===0)return counts.gains>0?1:0;
      if(counts.gains===0)return -1;
    }
    // A limit of zero can approach from either side. Use the largest
    // uncancelled absolute paired difference, not the magnitude of the limit.
    if(!context || typeof BenchRanks==="undefined")return null;
    const {run,snapshot,a,b}=context;
    const key=entry.key==="alignment"?"score":entry.key==="runtime"?"seconds":entry.key;
    const first=BenchRanks.measurements(run,snapshot,key,a);
    const second=BenchRanks.measurements(run,snapshot,key,b);
    if(first.some(x=>x.weight!==1)||second.some(x=>x.weight!==1))return null;
    const other=new Map(second.map(x=>[x.id,x.value]));
    const differences=first.filter(x=>other.has(x.id)).map(x=>
      entry.direction==="lower"?other.get(x.id)-x.value:x.value-other.get(x.id));
    return differences.length===entry.paired?tailSign(differences):null;
  }
  function casePsi(delta, exponent) {
    if(!Number.isFinite(delta))return null;
    if(delta===0)return 0;
    if(exponent===Infinity)return Math.sign(delta)*Infinity;
    if(exponent===0||exponent==="all")return Math.sign(delta);
    return Math.sign(delta)*Math.pow(Math.abs(delta),exponent);
  }
  function winner(result, reverse) {
    const wins=x=>["full-yes","observed-yes"].includes(x.kind)&&x.label==="YES";
    return wins(result)&&!wins(reverse)?1:wins(reverse)&&!wins(result)?-1:0;
  }
  function moment(entry, exponent, context) {
    // Ψ(r) is an average over PAIRED cases: p_i > 0 favours row A.
    // Multiple metrics cannot be summed: their scales and units differ.
    if (![0,1,2,Infinity].includes(exponent) || !entry ||
        !Number.isInteger(entry.paired) || entry.paired<1 ||
        !Number.isInteger(entry.expected) || entry.paired>entry.expected)
      return {value:null, paired:0, expected:entry?.expected||0};
    if(exponent===Infinity) {
      const sign=infinitySign(entry,context);
      return {value:sign===null?null:sign===0?0:sign*Infinity,
        paired:entry.paired,expected:entry.expected};
    }
    const proof=entry.proof || entry.subset?.proof;
    const direct=proof?.["psi"+exponent];
    let value=Number.isFinite(direct) ? direct : null;
    const counts=entry.observed;
    const valid=counts && [counts.gains,counts.losses,counts.ties]
      .every(x=>Number.isInteger(x)&&x>=0) &&
      counts.gains+counts.losses+counts.ties===entry.paired;
    if(value===null && valid) {
      if(exponent===0)value=(counts.gains-counts.losses)/entry.paired;
      if(exponent===1 && Number.isFinite(counts.mean_delta))
        value=counts.mean_delta;
      if(exponent===2 && entry.paired===1 &&
          Number.isFinite(counts.mean_delta)) {
        const d=counts.mean_delta;
        value=d*Math.abs(d);
      }
    }
    if(!Number.isFinite(value))value=null;
    return {value,paired:entry.paired,expected:entry.expected,
      observed:!["dominates","does-not-dominate"].includes(entry.status)};
  }
  function evaluate(report, a, b, selected, snapshot, run) {
    const entries = selected.map(({key,direction,label}) => ({
      key,label,direction, ...criterion(report,a,b,key,direction,snapshot,run)
    }));
    return {status:conjunction(entries), entries};
  }
  return {criterion,conjunction,evaluate,verdict,observedVerdict,evidence,moment,winner,tailSign,casePsi};
})();
if (typeof module !== "undefined") module.exports = BenchSubjects;

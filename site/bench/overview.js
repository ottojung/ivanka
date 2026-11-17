"use strict";
/* Scientific overview and minimal, cohort-agnostic unfinished-work notice. */
const BenchOverview = (() => {
  const LABELS={ivanka:"Ivanka",iva:"IVA",haploflow:"Haploflow",
    megahit:"MEGAHIT",abyss:"ABySS",spades:"SPAdes",velvet:"Velvet"};
  const COHORTS={real:"Physical",synthetic:"Synthetic"};
  const finite=x=>typeof x==="number"&&Number.isFinite(x);
  const caption=(list)=>list.map(x=>LABELS[x]||x).join(", ");
  function counts(run) {
    const expected=run.expected_sample_count||run.sample_count;
    return run.tool_progress||Object.fromEntries(run.tools.map(tool=>[
      tool,{expected,finished:(run.samples||[]).filter(s=>
        finite(s.score?.[tool])||s.failures?.includes(tool)).length,
        failed:(run.samples||[]).filter(s=>s.failures?.includes(tool)).length}
    ]));
  }
  function pending(run,scheduled) {
    if(!run) return [];
    const entries=counts(run);
    return (scheduled||run.tools).filter(tool=>
      entries[tool]&&entries[tool].finished<entries[tool].expected);
  }
  function median(numbers) {
    if(!numbers.length) return null;
    const sorted=[...numbers].sort((a,b)=>a-b);
    const middle=Math.floor(sorted.length/2);
    return sorted.length%2?sorted[middle]:
      (sorted[middle-1]+sorted[middle])/2;
  }
  function summary(run,diagnostics) {
    const aligned=BenchRanks.summary(run,diagnostics,"score","higher")
      .find(x=>x.mean!==null);
    const timed=BenchRanks.summary(run,diagnostics,"seconds","lower")
      .find(x=>x.mean!==null);
    const scores=run.tools.flatMap(tool=>
      BenchRanks.measurements(run,diagnostics,"score",tool)
        .flatMap(row=>Array(Math.min(400,row.weight)).fill(row.value)));
    const seconds=run.tools.flatMap(tool=>
      BenchRanks.measurements(run,diagnostics,"seconds",tool)
        .flatMap(row=>Array(Math.min(400,row.weight)).fill(row.value)));
    return {alignmentLeader:aligned||null,runtimeLeader:timed||null,
      medianAlignment:median(scores),medianRuntime:median(seconds)};
  }
  function coverage(run,tool,observed) {
    const expected=run.expected_sample_count||run.sample_count;
    if(counts(run)[tool]?.finished===expected || observed>=expected)
      return "";
    return observed+"/"+expected+" cases";
  }
  function notice(data,selected) {
    if(selected.archive)return null;
    const cohorts=Object.fromEntries((data.runs||[])
      .filter(r=>!r.archive&&r.cohort!=="combined")
      .map(r=>[r.cohort,r]));
    const workload=data.workload||{};
    const order=workload.order||["real","synthetic"];
    const deferred=new Set(workload.deferred||[]);
    const planned=Object.fromEntries(order.map(cohort=>[
      cohort,pending(cohorts[cohort],
        cohorts[cohort]?.tools.filter(t=>!deferred.has(t)))]));
    const remaining=order.filter(cohort=>planned[cohort]?.length);
    const notYet=order.some(cohort=>pending(cohorts[cohort]).length);
    if(!notYet)return null;
    const running=workload.running||{};
    const active=[];
    for(const cohort of order) {
      for(const tool of running[cohort]||[]) {
        if(!planned[cohort]?.includes(tool))continue;
        const measurement=counts(cohorts[cohort])[tool];
        active.push((COHORTS[cohort]||cohort)+" "+(LABELS[tool]||tool)+
          " ("+measurement.finished+"/"+measurement.expected+")");
      }
    }
    const result=["Benchmarks incomplete."];
    if(active.length)result.push("Running: "+active.join(", ")+".");
    else if(workload.status==="observed")
      result.push("No active MiCall containers at last update.");
    else result.push("Worker status unavailable.");
    const phase=remaining[0];
    if(phase) {
      const activeIn=new Set(running[phase]||[]);
      const waiting=planned[phase].filter(tool=>!activeIn.has(tool));
      if(waiting.length)
        result.push("Awaiting "+(COHORTS[phase]||phase).toLowerCase()+
          ": "+caption(waiting)+".");
      for(const later of remaining.slice(1))
        result.push((COHORTS[later]||later)+
          " measurements follow the earlier cohort.");
    }
    if(deferred.size && order.some(c=>pending(cohorts[c]).some(t=>
      deferred.has(t))))result.push("Deferred: "+caption([...deferred])+".");
    return result.join(" ");
  }
  return {counts,pending,median,summary,coverage,notice};
})();
if(typeof module!=="undefined")module.exports=BenchOverview;

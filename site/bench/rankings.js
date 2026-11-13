"use strict";
/* Numeric ordering of available measurements. A rank is not an all-r Ψ proof.
   Every mean reports its own sample count; missing values are never zero. */
const BenchRanks = (() => {
  const CORE = {
    score:{label:"Final MiCall alignment",unit:"alignment points",direction:"higher",
      stage:"Final MiCall dominant consensus",
      description:"Maximum local-alignment points across final MiCall MAX sequences and the reference panel.",
      denominator:"Observed successful, individually scored cases"},
    seconds:{label:"MiCall runtime",unit:"seconds",direction:"lower",
      stage:"In-container MiCall monotonic timer",
      description:"Wall-clock runtime inside the same MiCall pipeline. Lower means faster. Historical exploratory runtime with invalid timing is not displayed as valid.",
      denominator:"Observed successful, individually timed MiCall runs"}
  };
  const finite = x => typeof x==="number"&&Number.isFinite(x);
  const isCore = key => key==="score"||key==="seconds";
  function definition(key,catalog) {
    if (CORE[key]) return CORE[key];
    const x=catalog?.[key];
    if (!x) return null;
    return {label:x.label,unit:x.unit,stage:x.stage,
      description:x.description,denominator:x.denominator,
      direction:x.suggested_direction||"unspecified"};
  }
  function measurements(run,snapshot,key,tool) {
    if (!isCore(key)) {
      if (run.archive || (run.samples||[]).some(
        sample=>sample.diagnostics && Object.keys(sample.diagnostics).length)) {
        return (run.samples||[]).flatMap(sample=>{
          const value=sample.diagnostics?.[tool]?.[key];
          return finite(value)&&!sample.failures?.includes(tool)
            ?[{id:sample.alias,value,weight:1}]:[];
        });
      }
      if (snapshot?.run_id!==run.id) return [];
      const value=snapshot.tools?.[tool]?.values?.[key];
      return finite(value)?[{id:snapshot.sample_alias,value,weight:1}]:[];
    }
    if (run.hxb2_truth_verified||run.cohort==="real"||run.cohort==="combined") {
      return (run.samples||[]).flatMap(s=>{
        const value=s[key]?.[tool];
        return finite(value)&&!s.failures?.includes(tool)
          ?[{id:s.alias,value,weight:1}]:[];
      });
    }
    if (key==="seconds") return [];
    return (run.families||[]).flatMap(f=>{
      const value=f.scores?.[tool];
      const n=f.sample_count-(f.failures?.[tool]||0);
      return finite(value)&&n>0?[{id:f.family,value,weight:n}]:[];
    });
  }
  function summary(run,snapshot,key,direction) {
    const entries=run.tools.map(tool=>{
      const values=measurements(run,snapshot,key,tool);
      const observed=values.reduce((sum,x)=>sum+x.weight,0);
      const mean=observed?
        values.reduce((sum,x)=>sum+x.value*x.weight,0)/observed:null;
      return {tool,mean,observed,
        expected:run.expected_sample_count||run.sample_count};
    });
    const sortOrder=direction==="lower"?1:-1;
    entries.sort((a,b)=>a.mean===null?(b.mean===null?
      a.tool.localeCompare(b.tool):1):
      b.mean===null?-1:sortOrder*(a.mean-b.mean)||a.tool.localeCompare(b.tool));
    entries.forEach((item,index)=>{item.rank=index+1;});
    return entries;
  }
  function pairs(run,snapshot,key,direction,first,second) {
    const one=new Map(measurements(run,snapshot,key,first).map(x=>[x.id,x.value]));
    const two=new Map(measurements(run,snapshot,key,second).map(x=>[x.id,x.value]));
    const all=isCore(key)
      ?run.hxb2_truth_verified||run.cohort==="real"||run.cohort==="combined"
        ?run.samples.map(s=>({id:s.alias,detail:s}))
        :(run.families||[]).map(f=>({id:f.family,detail:f}))
      :run.archive || (run.samples||[]).some(s=>s.diagnostics)
        ?run.samples.map(s=>({id:s.alias,detail:s}))
      :snapshot?.run_id===run.id?[{id:snapshot.sample_alias,detail:null}]:[];
    return all.map(row=>{
      const a=one.has(row.id)?one.get(row.id):null;
      const b=two.has(row.id)?two.get(row.id):null;
      const available=a!==null&&b!==null;
      const delta=available?(direction==="lower"?b-a:a-b):null;
      return {id:row.id,first:a,rival:b,delta,failed:!available,
        detail:row.detail,unavailable:!available};
    });
  }
  return {CORE,isCore,definition,measurements,summary,pairs};
})();
if(typeof module!=="undefined")module.exports=BenchRanks;

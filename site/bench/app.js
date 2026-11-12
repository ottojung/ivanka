"use strict";
const el = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmt = (x, digits = 2) => Number.isFinite(x)
  ? Number(x).toLocaleString("en", { maximumFractionDigits: digits }) : "—";
const names = {iva:"IVA",ivanka:"Ivanka",haploflow:"Haploflow",megahit:"MEGAHIT",abyss:"ABySS",spades:"SPAdes",velvet:"Velvet"};
const state = {data:null,run:null,metric:"score",tool:null,sort:"id",reverse:false,rows:[]};

function currentRows() {
  let result;
  if (state.run.cohort === "real") {
    result = state.run.samples.map((s) => {
      const ivanka = s[state.metric].Ivanka, rival = s[state.metric][state.tool];
      return {id:s.alias,ivanka,rival,delta:state.metric === "score" ? ivanka-rival : rival-ivanka,
              failed:s.outcome !== "success",detail:s};
    });
  } else {
    result = state.metric === "seconds" ? [] : state.run.families.map((s) => ({
      id:s.family,ivanka:s.scores.ivanka,rival:s.scores[state.tool],
      delta:s.scores.ivanka-s.scores[state.tool],
      failed:s.failures.ivanka>0 || s.failures[state.tool]>0,detail:s
    }));
  }
  const query=el("search").value.trim().toLowerCase(), outcome=el("outcomeFilter").value;
  result = result.filter((r) => r.id.toLowerCase().includes(query) &&
    (outcome === "all" || outcome === classify(r)));
  result.sort((a,b) => {
    const order=state.sort==="id" ? a.id.localeCompare(b.id) : a[state.sort]-b[state.sort];
    return state.reverse ? -order : order;
  });
  state.rows=result;return result;
}

function classify(row) {
  if(row.failed)return "failure";
  if(Math.abs(row.delta)<1e-9)return "tie";
  return row.delta>0?"win":"loss";
}

function card(title,value,note) {
  return '<article class="metric-card"><div class="meta-label">'+esc(title)+'</div>'+
    '<div class="metric-value">'+esc(value)+'</div><div class="metric-note">'+esc(note)+'</div></article>';
}

function syncUrl() {
  const params=new URLSearchParams();
  params.set("run",state.run.id);
  if(state.metric==="seconds")params.set("metric","runtime");
  if(state.tool)params.set("competitor",state.tool);
  if(el("search").value)params.set("search",el("search").value);
  history.replaceState(null,"","?"+params.toString());
}

function drawOverview() {
  const run=state.run;
  el("runSelect").value=run.id;
  el("runCohort").textContent=run.cohort==="real"?"Real · MiCall":"Synthetic · diagnostic";
  el("runStatus").textContent=run.status==="passed-original-only"
    ?"Original PASS · expanded incomplete":"Ineligible · historical only";
  el("runStatus").className=run.status==="passed-original-only"?"status-pass":"status-no";
  el("runDate").textContent=run.date;
  el("runDescription").textContent=run.status_reason;
  el("globalNotice").textContent="Expanded qualification: INCOMPLETE. The old 400-case random-genome cohort is ineligible under Intent 008. The original 198-real IVA gate separately passed.";
  if(run.cohort==="real") {
    const wins=run.samples.filter((s)=>s.seconds.Ivanka<s.seconds.IVA).length;
    el("metricCards").innerHTML=card("Physical MiCall cases","198 / 198","Independently verified original reads")+
      card("Runtime wins",wins+" / 198","Ivanka faster than IVA")+
      card("Mean time advantage",fmt(run.psi.runtime.psi1)+" s","MiCall monotonic time per sample")+
      card("Alignment Ψ(1)","+"+fmt(run.psi.alignment.psi1,3),"Both all-r gates passed");
  } else {
    const fails=run.families.reduce((total,f)=>total+Object.values(f.failures).reduce((a,b)=>a+b,0),0);
    el("metricCards").innerHTML=card("Legacy cases","400","Disallowed random genomic truth")+
      card("Competitors","7","Exploratory CLI runs only")+
      card("Failed tool runs",String(fails),"Failures are not wins")+
      card("Expanded Ψ verdict","NOT PASSED","No qualifying synthetic data");
  }
}

function drawCompare() {
  const run=state.run;
  el("scoreView").classList.toggle("active",state.metric==="score");
  el("timeView").classList.toggle("active",state.metric==="seconds");
  if(run.cohort==="synthetic" && state.metric==="seconds") {
    el("comparisonContext").textContent="Historical synthetic runtimes are invalid.";
    el("comparisonChart").innerHTML='<p class="hint">No valid runtime comparison. The exploratory runner included truth-scoring time in reported durations.</p>';
    return;
  }
  const values=run.tools.map((tool)=>{
    let value=0,failures=0;
    if(run.cohort==="real") {
      value=run.samples.reduce((sum,s)=>sum+s[state.metric][tool],0)/run.samples.length;
    } else {
      value=run.families.reduce((sum,f)=>sum+f.scores[tool],0)/run.families.length;
      failures=run.families.reduce((sum,f)=>sum+f.failures[tool],0);
    }
    return {tool,value,failures};
  });
  const largest=Math.max(1e-9,...values.map((r)=>r.value));
  const suffix=state.metric==="seconds"?" s":"";
  el("comparisonChart").innerHTML=values.map((r)=>
    '<div class="bar-line"><span class="bar-name">'+esc(names[r.tool.toLowerCase()]||r.tool)+'</span>'+
    '<div class="bar-track"><div class="bar-fill '+(r.tool.toLowerCase()==="ivanka"?"":"other")+
    '" style="width:'+(r.value*100/largest).toFixed(2)+'%"></div></div>'+
    '<span class="bar-value">'+fmt(r.value,3)+suffix+'</span></div>'+
    (r.failures?'<p class="bar-note">'+r.failures+' tool failures — not a passing comparison</p>':"")
  ).join("")+'<p class="plot-caption">'+(state.metric==="score"
    ?'Real scores: MiCall final MAX points. Synthetic scores: global similarity fraction. Do not pool these scales.'
    :'Mean monotonic MiCall runtime in seconds; lower is better.')+'</p>';
  el("comparisonContext").textContent=run.cohort==="real"
    ?"Original 198-sample IVA-only comparison; expanded six-rival real comparison remains incomplete."
    :"Historical known-truth synthetic diagnostics; disallowed genomic-truth cohort.";
}

function drawEvidence() {
  const run=state.run;
  if(run.cohort!=="real") {
    el("evidenceContent").innerHTML='<article class="evidence-card"><h3>Historical synthetic dataset</h3>'+
      '<div class="verdict no">NOT QUALIFIED</div><p class="hint">The random nucleotide truth, failed tools and invalid runtimes make this an exploratory diagnostic, not a scientific benchmark pass.</p></article>';
    return;
  }
  function one(label,p) {
    return '<article class="evidence-card"><h3>'+esc(label)+'</h3><div class="verdict">'+
      'PASS · Ψ(r) &gt; 0 for all r ≥ 0</div><p class="hint">'+p.gains+' gains · '+
      p.losses+' losses · '+p.ties+' ties. Independently verified, no nonnegative zeros.</p>'+
      '<div class="psi-values"><div><b>'+fmt(p.psi0,4)+'</b><span>Ψ(0)</span></div>'+
      '<div><b>'+fmt(p.psi1,4)+'</b><span>Ψ(1)</span></div>'+
      '<div><b>'+fmt(p.psi2,3)+'</b><span>Ψ(2)</span></div></div></article>';
  }
  el("evidenceContent").innerHTML='<div class="evidence-grid">'+
    one("01 · ALIGNMENT",run.psi.alignment)+one("02 · RUNTIME",run.psi.runtime)+
    '</div><p class="hint">This only certifies the original 198-sample IVA comparison. It is not a seven-way qualification or clinical authorization.</p>';
}

function drawTable() {
  const rows=currentRows();
  const suffix=state.metric==="seconds"?" s":"";
  el("resultRows").innerHTML=rows.map((r)=>{
    const outcome=classify(r), tone=outcome==="win"?"positive":outcome==="loss"?"negative":"neutral";
    return '<tr tabindex="0" role="button" data-alias="'+esc(r.id)+'" aria-label="Inspect '+esc(r.id)+'">'+
      '<td class="cell-title">'+esc(r.id)+'</td>'+
      '<td class="number">'+fmt(r.ivanka,3)+suffix+'</td>'+
      '<td class="number">'+fmt(r.rival,3)+suffix+'</td>'+
      '<td class="number '+tone+'">'+(r.delta>0?"+":"")+fmt(r.delta,3)+suffix+'</td>'+
      '<td class="'+tone+'">'+outcome+'</td></tr>';
  }).join("")||'<tr><td colspan="5">No matching cases.</td></tr>';
  el("resultCount").textContent=rows.length+" visible of "+
    (state.run.cohort==="real"?state.run.samples.length:state.run.families.length);
  el("resultsTable").querySelectorAll("tr[data-alias]").forEach((node)=>{
    const show=()=>showDetail(rows.find((r)=>r.id===node.dataset.alias));
    node.addEventListener("click",show);
    node.addEventListener("keydown",(event)=>{
      if(["Enter"," "].includes(event.key)){event.preventDefault();show();}
    });
  });
}

function showDetail(row) {
  if(!row)return;
  const x=row.detail;
  let detail;
  if(state.run.cohort==="real") {
    detail='<p>Ivanka: '+fmt(x.score.Ivanka,3)+' points, '+fmt(x.seconds.Ivanka,3)+' s. '+
      'IVA: '+fmt(x.score.IVA,3)+' points, '+fmt(x.seconds.IVA,3)+' s.</p>'+
      '<p>90% floor: '+(x.floor_ok?"PASS":"FAIL")+'. Sample alias is not a source file name or patient identifier.</p>';
  } else {
    detail='<p>Mean across '+x.sample_count+' historical cases. Competitor failures: '+
      x.failures[state.tool]+'. Ivanka failures: '+x.failures.ivanka+'.</p>';
  }
  el("detailPanel").innerHTML='<h3>'+esc(row.id)+' · '+classify(row)+'</h3>'+detail;
  el("detailPanel").hidden=false;
}

function drawProvenance() {
  const r=state.run;
  const fields=[["Run",r.id],["Source commit",r.source_commit],
    ["Samples",String(r.sample_count)],["Expanded eligibility",r.eligible_for_expanded?"Eligible":"Not eligible"]];
  for(const [label,key] of [["Manifest SHA256","manifest_sha256"],["Result SHA256","results_sha256"],
    ["Independent certificate SHA256","certificate_sha256"],["Diagnostic SHA256","diagnostic_sha256"]]){
    if(r[key])fields.push([label,r[key]]);
  }
  for(const [tool,ref] of Object.entries(r.images||{})) {
    fields.push([tool+" pinned image",typeof ref==="string"?ref:JSON.stringify(ref)]);
  }
  el("provenanceContent").innerHTML='<div class="provenance-box"><dl>'+fields.map(([k,v])=>
    '<dt>'+esc(k)+'</dt><dd>'+esc(v)+'</dd>').join("")+'</dl></div>';
}

function render() {
  const run=state.run;
  const tools=run.tools.filter((t)=>t.toLowerCase()!=="ivanka");
  if(!tools.includes(state.tool))state.tool=tools[0];
  el("runSelect").value=run.id;
  el("comparisonTool").innerHTML=tools.map((tool)=>
    '<option value="'+esc(tool)+'">'+esc(names[tool.toLowerCase()]||tool)+'</option>').join("");
  el("comparisonTool").value=state.tool;
  drawOverview();drawCompare();drawEvidence();drawTable();drawProvenance();syncUrl();
}

function exportCsv() {
  const metric=state.metric==="score"?"alignment":"runtime_seconds";
  const header=["alias","ivanka_"+metric,state.tool+"_"+metric,"ivanka_advantage","outcome"];
  const values=[header.join(",")].concat(state.rows.map((r)=>
    [r.id,r.ivanka,r.rival,r.delta,classify(r)].join(",")));
  const href=URL.createObjectURL(new Blob([values.join("\n")+"\n"],{type:"text/csv"}));
  const link=document.createElement("a");
  link.href=href;link.download=state.run.id+"-"+metric+".csv";
  document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(href);
}

function bind() {
  el("runSelect").addEventListener("change",()=>{
    state.run=state.data.runs.find((r)=>r.id===el("runSelect").value);
    state.metric="score";state.tool=null;el("search").value="";el("outcomeFilter").value="all";
    el("detailPanel").hidden=true;render();
  });
  for(const [id,metric] of [["scoreView","score"],["timeView","seconds"]]) {
    el(id).addEventListener("click",()=>{
      state.metric=metric;drawCompare();drawTable();syncUrl();
    });
  }
  el("comparisonTool").addEventListener("change",()=>{state.tool=el("comparisonTool").value;drawTable();syncUrl();});
  el("outcomeFilter").addEventListener("change",drawTable);
  el("search").addEventListener("input",()=>{drawTable();syncUrl();});
  el("exportCsv").addEventListener("click",exportCsv);
  document.querySelectorAll("th button[data-sort]").forEach((button)=>
    button.addEventListener("click",()=>{
      state.reverse=state.sort===button.dataset.sort?!state.reverse:false;
      state.sort=button.dataset.sort;drawTable();
    }));
}

async function main() {
  bind();
  try {
    const response=await fetch("./data/runs.json",{cache:"no-store"});
    if(!response.ok)throw new Error("HTTP "+response.status);
    state.data=await response.json();
    if(state.data.schema!=="ivanka.assembler-bench.public.v1"||
       !Array.isArray(state.data.runs)||!state.data.runs.length)
      throw new Error("Unsupported or missing public data");
    el("runSelect").innerHTML=state.data.runs.map((r)=>
      '<option value="'+esc(r.id)+'">'+esc(r.title)+'</option>').join("");
    el("runSelect").disabled=false;
    const params=new URLSearchParams(location.search);
    state.run=state.data.runs.find((r)=>r.id===params.get("run"))||state.data.runs[0];
    state.metric=params.get("metric")==="runtime"?"seconds":"score";
    state.tool=params.get("competitor");
    el("search").value=params.get("search")||"";
    render();
  } catch(error) {
    el("globalNotice").textContent="Results unavailable: "+error.message+
      ". No qualification is claimed.";
  }
}
main();

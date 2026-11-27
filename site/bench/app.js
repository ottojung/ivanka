"use strict";
const el = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmt = (x, digits = 2) => Number.isFinite(x)
  ? Number(x).toLocaleString("en", { maximumFractionDigits: digits }) : "—";
const fmtPsi = x => {
  if(x===Infinity)return "+∞";
  if(x===-Infinity)return "−∞";
  if(!Number.isFinite(x))return "—";
  if(x===0)return "0";
  const abs=Math.abs(x);
  const value=(abs<0.0001||abs>=1000000)
    ?x.toExponential(3).replace("e+","e")
    :x.toLocaleString("en",{maximumSignificantDigits:4});
  return x>0?"+"+value:value;
};
// Apply only to already escaped text, keeping mathematical glyphs legible.
const infinityMarkup = escaped => escaped.replaceAll("∞",
  '<span class="infinity-symbol">∞</span>');
// Display names are presentation only. Roster membership is never read from
// this map: selectors, matrix axes, plots and headings come from run.tools.
// A cohort may publish its own labels; opaque ids fall back to a readable form.
const DISPLAY_NAMES = {iva:"IVA",ivanka:"Ivanka",haploflow:"Haploflow",
  megahit:"MEGAHIT",abyss:"ABySS",spades:"SPAdes",velvet:"Velvet"};
function toolLabel(tool) {
  const id=String(tool??"").toLowerCase();
  const published=state.run?.tool_labels?.[id]||state.run?.tool_names?.[id];
  if(typeof published==="string"&&published)return published;
  return DISPLAY_NAMES[id]||
    id.replace(/[_-]+/g," ").replace(/\b[a-z]/g,c=>c.toUpperCase());
}
// Method type is a property of the measurement, not a separate roster panel.
// A reference-based method is displayed beside de novo tools but named as
// such everywhere a tool name appears, including ranking and matrix headers.
function toolMethod(tool) {
  return state.run?.tool_modes?.[String(tool??"").toLowerCase()]||null;
}
function toolLabelHtml(tool) {
  const mode=toolMethod(tool);
  const badge=mode&&mode.kind
    ?' <span class="method-badge" title="'+esc(mode.description||mode.kind)+
      '">'+esc(mode.kind)+(mode.de_novo===false?' · not de novo':'')+'</span>'
    :"";
  return esc(toolLabel(tool))+badge;
}
// An unavailable measurement is shown as N/A. It is never rendered as zero
// and never enters a mean, distribution or paired difference.
function na(value,digits=5) {
  return Number.isFinite(value)?fmt(value,digits):"N/A";
}
function methodNotes() {
  const modes=state.run?.tool_modes||{};
  return Object.entries(modes).map(([tool,mode])=>
    '<p class="method-note"><strong>'+toolLabelHtml(tool)+'</strong>: '+
    esc(mode.description||"Method type recorded with this cohort.")+
    ' Metrics that require native or unstitched contigs are N/A.</p>').join("");
}
const state = {data:null,run:null,metric:"score",firstTool:null,tool:null,
  sort:"id",reverse:false,rows:[],diagnostics:null,
  direction:"higher",psiExponent:"1",mode:"total",
  totalTool:null,distributionTool:null};

function metricInfo() {
  return BenchRanks.definition(state.metric,state.diagnostics?.metric_catalog);
}
function primarySubject() {
  const key=state.metric==="score"?"alignment":state.metric==="seconds"?"runtime":state.metric;
  return {key,label:metricInfo()?.label||key,direction:state.direction};
}
function caseExponent() {
  return state.psiExponent==="all"?"all":Number(state.psiExponent);
}
function caseRows() {
  if(state.mode==="total")return state.totalTool?
    BenchRanks.cases(state.run,state.diagnostics,state.metric,state.totalTool):[];
  if(!state.firstTool||!state.tool)return [];
  return BenchRanks.pairs(state.run,state.diagnostics,state.metric,
    state.direction,state.firstTool,state.tool).map(row=>
    ({...row,psi:BenchSubjects.casePsi(row.delta,caseExponent())}));
}
function currentRows() {
  const query=el("search").value.trim().toLowerCase();
  const total=state.mode==="total";
  const outcome=el(total?"measurementFilter":"outcomeFilter").value;
  const rows=caseRows().filter(row=>{
    if(!row.id.toLowerCase().includes(query) &&
       !(row.detail?.family||"").toLowerCase().includes(query))return false;
    if(outcome==="all")return true;
    if(total){
      if(outcome==="failure")return failedArm(row.detail,state.totalTool);
      return outcome==="available"?!row.unavailable:row.unavailable;
    }
    if(outcome==="floor")return state.metric==="score" &&
      row.detail?.floor_ok===false;
    return outcome===classify(row);
  });
  rows.sort((a,b)=>{
    const sort=state.sort;
    const value=x=>sort==="id"?x.id:x[sort];
    const left=value(a),right=value(b);
    const cmp=sort==="id"?left.localeCompare(right):
      left===null?right===null?0:1:right===null?-1:left===right?0:left<right?-1:1;
    return state.reverse?-cmp:cmp;
  });
  state.rows=rows;
  return rows;
}
function failedArm(detail,tool) {
  const failures=detail?.failures;
  return Array.isArray(failures)?failures.includes(tool):Boolean(failures?.[tool]>0);
}
function classify(row) {
  if(row.unavailable) {
    const failures=row.detail?.failures;
    const affected=Array.isArray(failures)
      ?failures.includes(state.firstTool)||failures.includes(state.tool)
      :failures&&(failures[state.firstTool]>0||failures[state.tool]>0);
    return affected?"failure":"unavailable";
  }
  if(row.delta===0)return "tie";
  return row.delta>0?"win":"loss";
}
function metricOptions() {
  const select=el("diagnosticMetric");
  const catalog=state.diagnostics?.metric_catalog||{};
  const options=[["score","Final MiCall alignment"],["seconds","MiCall runtime"],
    ...Object.entries(catalog).map(([key,value])=>[key,value.label])];
  if(select.options.length!==options.length) {
    select.innerHTML=options.map(([key,label])=>'<option value="'+esc(key)+
      '">'+esc(label)+'</option>').join("");
  }
  if(!BenchRanks.definition(state.metric,catalog)){state.metric="score";state.direction="higher";}
  select.value=state.metric;
  const order=el("singleDirection");
  order.value=state.direction;
}
function preferredDirection(key) {
  const suggested=BenchRanks.definition(key,state.diagnostics?.metric_catalog)
    ?.direction;
  return suggested==="lower"?"lower":"higher";
}

function card(title,value,note) {
  return '<article class="metric-card"><div class="meta-label">'+esc(title)+'</div>'+
    '<div class="metric-value">'+esc(value)+'</div><div class="metric-note">'+esc(note)+'</div></article>';
}

function syncUrl() {
  if(!state.run)return;
  const params=new URLSearchParams();
  params.set("run",state.run.id);
  params.set("mode",state.mode);
  if(state.totalTool)params.set("assembler",state.totalTool);
  params.set("metric",state.metric==="score"?"alignment":
    state.metric==="seconds"?"runtime":state.metric);
  params.set("order",state.direction);
  if(state.firstTool)params.set("first",state.firstTool);
  if(state.tool)params.set("competitor",state.tool);
  if(el("search").value)params.set("search",el("search").value);
  params.set("psi_r",state.psiExponent);
  params.set("subjects",selectedSubjects().map(({key,direction})=>
    key+":"+direction).join(","));
  history.replaceState(null,"","?"+params.toString());
}

function coverageStatus(run) {
  const progress=run.tool_progress||{};
  const tools=Array.isArray(run.tools)?run.tools:[];
  let expected=0,finished=0,failed=0;
  for(const tool of tools) {
    const p=progress[tool]||{};
    expected+=Number(p.expected||run.expected_sample_count||run.sample_count||0);
    finished+=Number(p.finished||0);
    failed+=Number(p.failed||0);
  }
  if(!expected) {
    const samples=Array.isArray(run.samples)?run.samples.length:0;
    return {text:samples? samples+" cases":"No measurements", cls:"status-neutral"};
  }
  const text=finished+"/"+expected+" measured";
  const cls=finished>=expected?"status-complete":finished>0?"status-partial":"status-neutral";
  return {text:failed?text+" · "+failed+" failed":text, cls};
}

function drawOverview() {
  const run=state.run,previous=!!run.archive;
  const cohortLabel=run.cohort==="combined"?"Combined cohort":
    run.cohort==="real"?"Physical cohort":
    run.cohort==="synthetic"?"Synthetic cohort":
    (run.cohort_label||String(run.cohort||"Cohort"));
  const descriptions={
    synthetic:"Final MiCall MAX sequences scored by local alignment to their HXB2-derived generating truth; runtime measured in-container.",
    real:"Final MiCall MAX sequences scored against the fixed HIV/HCV reference panel; runtime measured in-container.",
    combined:"Physical and synthetic MiCall scores and runtimes combined without changing the per-case measurements."
  };
  el("runSelect").value=run.id;
  el("runCohort").textContent=cohortLabel;
  const cov=coverageStatus(run);
  el("runStatus").textContent=previous?"Historical · "+cov.text:cov.text;
  el("runStatus").className=previous?"status-neutral":cov.cls;
  el("runDate").textContent=run.date||"—";
  const rosterNote=el("rosterNote");
  if(rosterNote)rosterNote.textContent=run.tools.length+" assemblers in this cohort.";
  el("runDescription").textContent=run.description||descriptions[run.cohort]||
    "Alignment and independently timed execution measurements for the selected cohort.";
  const note=BenchOverview.notice(state.data,run);
  const notice=el("globalNotice");
  notice.hidden=!note;
  if(note) {
    const published=state.data.published_at;
    notice.textContent=note+(published
      ?" · Data published "+new Date(published).toLocaleString()+".":"");
  }
  const overview=BenchOverview.summary(run,state.diagnostics);
  const lead=overview.alignmentLeader,fast=overview.runtimeLeader;
  el("metricCards").innerHTML=
    card("Highest mean alignment",lead?fmt(lead.mean,1)+" points":"—",
      lead?toolLabel(lead.tool):"No alignment measurements")+
    card("Lowest mean runtime",fast?fmt(fast.mean,1)+" s":"—",
      fast?toolLabel(fast.tool):"No runtime measurements")+
    card("Median alignment",overview.medianAlignment===null?"—":
      fmt(overview.medianAlignment,1)+" points",
      "Across recorded final MAX alignments")+
    card("Median MiCall runtime",overview.medianRuntime===null?"—":
      fmt(overview.medianRuntime,1)+" s",
      "Across recorded in-container durations");
}

function drawCompare() {
  const info=metricInfo();
  const ranking=BenchRanks.summary(state.run,state.diagnostics,
    state.metric,state.direction);
  const valid=ranking.filter(x=>x.mean!==null);
  const cap=Math.max(1e-12,...valid.map(x=>Math.abs(x.mean)));
  const label=state.direction==="lower"?"Lowest first":"Highest first";
  el("comparisonContext").textContent=info.label+" · "+label+
    " · average across measured cases ("+info.unit+").";
  el("comparisonChart").innerHTML=ranking.map(row=>{
    const incomplete=BenchOverview.coverage(state.run,row.tool,row.observed);
    return '<button type="button" class="bar-line rank-trigger" data-tool="'+
    esc(row.tool)+'" aria-pressed="'+(row.tool===state.totalTool)+'" aria-label="Show '+esc(toolLabel(row.tool))+
    ' '+esc(info.label)+' distribution">'+
    '<span class="bar-name">'+row.rank+'. '+
    toolLabelHtml(row.tool)+'</span>'+
    '<span class="bar-track"><span class="bar-fill '+
    (row.tool===state.totalTool?"":"other")+'" style="width:'+
    (row.mean===null?0:100*Math.abs(row.mean)/cap).toFixed(2)+'%"></span></span>'+
    '<span class="bar-value">'+(row.mean===null?"—":fmt(row.mean,5))+'</span>'+
    '<span class="bar-count">'+esc(incomplete)+'</span>'+
    '</button>';
  }).join("")+
    '<p class="plot-caption">Select an assembler to view its distribution and individual cases.</p>';
  el("comparisonChart").querySelectorAll("button[data-tool]").forEach(button=>
    button.addEventListener("click",()=>{
      state.totalTool=button.dataset.tool;
      state.distributionTool=state.totalTool;
      drawCompare();drawTable();syncUrl();
    }));
  drawDistribution();

}
function drawExactProfiles(tool) {
  const holder=el("exactProfileChart");
  const cases=(state.run.samples||[]).map(s=>s.exact_profiles?.[tool])
    .filter(p=>p&&Array.isArray(p.full_span)&&Array.isArray(p.inner_70)
      &&p.full_span.length&&p.inner_70.length);
  if(!state.metric.startsWith("exact_coverage") || !cases.length) {
    holder.hidden=true;
    return;
  }
  const length=64, means=[Array(length).fill(0),Array(length).fill(0)];
  const tracks=["full_span","inner_70"];
  for(const item of cases) {
    tracks.forEach((track,index)=>{
      const data=item[track];
      for(let i=0;i<length;i++) {
        const val=data[Math.min(data.length-1,Math.floor(
          (i+.5)*data.length/length))];
        if(Number.isFinite(val)&&val>=0)means[index][i]+=val;
      }
    });
  }
  means.forEach(track=>track.forEach((v,i)=>track[i]=v/cases.length));
  const top=12,bottom=185,left=60,right=704;
  const max=Math.max(1,...means.flat())*1.06;
  const x=i=>left+i*(right-left)/(length-1);
  const y=v=>bottom-v/max*(bottom-top);
  const curves=means.map((array,index)=>
    '<path class="exact-profile '+(index?"inner":"full")+'" d="'+
    array.map((v,i)=>(i?"L":"M")+x(i).toFixed(1)+","+
      y(v).toFixed(1)).join(" ")+'"></path>').join("");
  holder.innerHTML='<h4>Exact-read coverage along the final consensus</h4>'+
    '<svg viewBox="0 0 735 220" role="img" aria-label="'+
    esc("Mean exact full-span and interior coverage profiles for "+
      cases.length+" measured "+toolLabel(tool)+" cases")+'">'+
    '<line class="distribution-axis" x1="'+left+'" x2="'+right+
    '" y1="'+bottom+'" y2="'+bottom+'"/>'+curves+
    '<text x="'+left+'" y="208">Start</text>'+
    '<text x="'+right+'" y="208" text-anchor="end">End</text>'+
    '</svg><p class="distribution-legend">'+cases.length+
    ' cases · mean depth across relative sequence position · '+
    '<span class="profile-full">Full read</span> · '+
    '<span class="profile-inner">Interior (70-nt ends excluded)</span></p>';
  holder.hidden=false;
}

function drawDistribution() {
  const tool=state.distributionTool, panel=el("distributionPanel");
  if(!tool || !state.run.tools.includes(tool)) {
    panel.hidden=true;
    return;
  }
  const info=metricInfo();
  const readings=BenchRanks.measurements(
    state.run,state.diagnostics,state.metric,tool);
  const values=readings.flatMap(row=>
    Array.from({length:Math.min(400,row.weight)},()=>row.value));
  const result=BenchDistribution.model(values);
  const label=toolLabel(tool);
  el("distributionTitle").textContent=label+" · "+info.label;
  el("distributionSummary").textContent=result.n+
    " measured cases · "+info.unit+
    (result.n?" · range "+fmt(result.min,4)+"–"+fmt(result.max,4):"");
  panel.hidden=false;
  drawExactProfiles(tool);
  document.querySelectorAll("#comparisonChart button[data-tool]").forEach(
    button=>button.setAttribute("aria-pressed",String(button.dataset.tool===state.totalTool)));
  if(!result.n) {
    el("distributionChart").textContent="No measurements for this assembler.";
    return;
  }
  const left=65,right=705,top=14,bottom=220;
  const height=bottom-top, width=right-left;
  const maxDensity=Math.max(1e-12,
    ...result.bins.map(x=>x.density),
    ...result.curve.map(x=>x.y))*1.12;
  const [min,max]=result.range;
  const x=v=>left+(v-min)/(max-min)*width;
  const y=v=>bottom-v/maxDensity*height;
  const bars=result.bins.map(bin=>
    '<rect x="'+x(bin.from).toFixed(2)+'" y="'+y(bin.density).toFixed(2)+
    '" width="'+Math.max(0,x(bin.to)-x(bin.from)-.75).toFixed(2)+
    '" height="'+Math.max(0,bottom-y(bin.density)).toFixed(2)+
    '" class="distribution-bin"><title>'+bin.count+
    ' cases · '+fmt(bin.from,4)+' to '+fmt(bin.to,4)+'</title></rect>').join("");
  const density=result.curve.length?
    '<path class="distribution-kde" d="'+result.curve.map((p,i)=>
      (i?"L":"M")+x(p.x).toFixed(2)+","+y(p.y).toFixed(2)).join(" ")+'"></path>':"";
  const ticks=[min,(min+max)/2,max].map(v=>
    '<text x="'+x(v).toFixed(2)+'" y="243" text-anchor="middle">'+
    esc(fmt(v,4))+'</text>').join("");
  el("distributionChart").innerHTML=
    '<svg viewBox="0 0 735 263" role="img" aria-label="'+
    esc(label+" "+info.label+" histogram and kernel density estimate")+'">'+
    '<line x1="'+left+'" x2="'+right+'" y1="'+bottom+'" y2="'+bottom+
    '" class="distribution-axis"/>'+bars+density+ticks+
    '</svg><p class="distribution-legend">Histogram · '+
    (result.curve.length?"Gaussian KDE":"KDE unavailable for constant or single-case values")+
    '</p>';
}

function drawDiagnostics() {
  const info=metricInfo();
  const ranking=BenchRanks.summary(state.run,state.diagnostics,
    state.metric,state.direction);
  el("diagnosticExplanation").innerHTML=
    '<div class="metric-explanation-head"><h3>'+esc(info.label)+'</h3>'+
    '<span>'+esc(info.unit)+'</span></div>'+
    '<p>'+esc(info.description)+'</p>'+
    '<dl><dt>Stage</dt><dd>'+esc(info.stage)+'</dd>'+
    '<dt>Unit</dt><dd>'+esc(info.unit)+'</dd>'+
    '<dt>Denominator / basis</dt><dd>'+esc(info.denominator)+'</dd>'+
    '<dt>Observed cases</dt><dd>'+ranking.reduce((n,r)=>
      n+Number(r.observed>0),0)+' of '+ranking.length+
    ' methods have measurements in this run</dd></dl>'+
    methodNotes();
}

function drawTable() {
  const rows=currentRows(),total=state.mode==="total";
  const info=metricInfo(),r=caseExponent();
  const exponent=r===Infinity?"∞":r==="all"?"All":String(r);
  const suffix=info?.unit==="seconds"?" s":"";
  const chosen=total?state.totalTool:state.firstTool&&state.tool;
  el("redCaseHeading").hidden=total;
  el("psiCaseHeading").hidden=total;
  el("firstColumn").classList.toggle("assembler-blue",!total);
  el("firstColumn").innerHTML=total?(chosen?toolLabelHtml(state.totalTool):"Assembler")+' <span>↕</span>':
    'Assembler Blue'+(chosen?' · '+toolLabelHtml(state.firstTool):'')+' <span>↕</span>';
  el("secondColumn").innerHTML='Assembler Red'+(chosen&&!total?' · '+toolLabelHtml(state.tool):'')+' <span>↕</span>';
  el("psiColumn").innerHTML='Ψ('+infinityMarkup(esc(exponent))+') <span>↕</span>';
  el("caseContext").innerHTML=total?
    (chosen?esc(toolLabel(state.totalTool)+" · "+info.label+" ("+info.unit+")"):
      "Select an assembler in the ranking above."):
    chosen?esc(info.label+" · "+state.direction+" preferred · ")+
    (r==="all"?"Single-case strict all-r verdict (YES, NO, or tie).":
      "Each case contributes sign(p) × |p|"+(r===Infinity?" as r → "+infinityMarkup("∞")+" (eventual sign).":'<sup>'+esc(r)+'</sup>.'))+
    (selectedSubjects().length?" Additional requirements affect the matrix only.":""):
    "Choose a pair in the matrix above.";
  el("exportCsv").disabled=!chosen;
  el("resultRows").innerHTML=rows.map(row=>{
    const tone=row.psi>0?"assembler-blue":row.psi<0?"assembler-red":"neutral";
    const value=row.psi===null?"N/A":r==="all"?
      (row.psi>0?"YES":row.psi<0?"NO":"0"):fmtPsi(row.psi);
    return '<tr tabindex="0" role="button" data-alias="'+esc(row.id)+
      '" aria-label="Inspect '+esc(row.id)+'">'+
      '<td class="cell-title">'+esc(row.id)+'</td>'+
      '<td class="number">'+na(row.first)+(Number.isFinite(row.first)?suffix:"")+'</td>'+
      (total?'':'<td class="number">'+na(row.rival)+(Number.isFinite(row.rival)?suffix:"")+'</td>'+
      '<td class="number '+tone+'">'+infinityMarkup(esc(value))+'</td>')+'</tr>';
  }).join("")||'<tr><td colspan="'+(total?2:4)+'">'+(chosen?"No matching measurements.":total?"Select an assembler in the ranking.":"Select an assembler pair in the matrix.")+'</td></tr>';
  el("resultCount").textContent=chosen?rows.length+" visible of "+
    caseRows().length+
    " available case/family records for "+info.label:total?"No assembler selected":"No pair selected";
  el("resultsTable").querySelectorAll("tr[data-alias]").forEach(node=>{
    const show=()=>showDetail(rows.find(row=>row.id===node.dataset.alias));
    node.addEventListener("click",show);
    node.addEventListener("keydown",event=>{
      if(["Enter"," "].includes(event.key)){event.preventDefault();show();}
    });
  });
}

function showDetail(row) {
  if(!row)return;
  const dialog=el("sampleDialog"),detail=row.detail;
  const a=state.mode==="total"?state.totalTool:state.firstTool,b=state.mode==="total"?null:state.tool;
  el("sampleDialogTitle").textContent=row.id+" · All recorded metrics";
  const failures=Array.isArray(detail?.failures)?detail.failures:Object.keys(detail?.failures||{}).filter(key=>detail.failures[key]>0);
  const provenance=detail?.family?" · Family: "+detail.family:"";
  const floor=detail?.floor_ok===null||detail?.floor_ok===undefined
    ?"unresolved":detail.floor_ok?"met":"not met";
  el("sampleDialogSummary").textContent=toolLabel(a)+(b?" vs "+toolLabel(b):"")+provenance+" · 90% alignment floor: "+floor+
    " · Failed arms: "+(failures.length?failures.join(", "):"none")+".";
  el("sampleDialogMetrics").innerHTML=BenchViews.sampleTable(
    state.run,state.diagnostics,row.id,a,b);
  if(!dialog.open)dialog.showModal();
}

function drawProvenance() {
  const r=state.run;
  const fields=[["Run",r.id],["Source commit",r.source_commit],
    ["Samples",String(r.sample_count)]];
  if(r.archive) {
    fields.push(["Execution manifest SHA256",r.archive.manifest_sha256],
      ["Execution results SHA256",r.archive.results_sha256],
      ["Source attestation SHA256",r.archive.source_attestation_sha256]);
  }
  for(const [label,key] of [["Manifest SHA256","manifest_sha256"],
    ["HXB2 cohort SHA256","cohort_manifest_sha256"],
    ["Benchmark source SHA256","source_manifest_sha256"],
    ["Result SHA256","results_sha256"],
    ["Proof SHA256","certificate_sha256"],
    ["Diagnostic SHA256","diagnostic_sha256"]]) {
    if(r[key])fields.push([label,r[key]]);
  }
  const inventory=r.micall_fork_provenance?.images||{};
  const roster=new Map((r.roster||[]).map(item=>[item.id,item]));
  const buildLinks=r.tools?.length?
    '<section class="dedicated-builds"><h3>Assembler builds</h3>'+
    '<div class="table-scroll provenance-scroll"><table class="dedicated-table"><thead><tr>'+
    '<th>Assembler</th><th>Dedicated fork branch</th>'+
    '<th>Fork source commit</th><th>Immutable image ID</th></tr></thead><tbody>'+
    r.tools.map(name=>{
      const provenance=roster.get(name)?.provenance||{};
      const adapter=provenance.adapter_commit;
      const item=inventory[name]||{
        source_branch:provenance.source_branch,
        source_commit:adapter,
        source_url:provenance.source_url||(/^[a-f0-9]{40}$/.test(adapter||"")?
          "https://github.com/ottojung/MiCall/tree/"+adapter:null),
        image_sha256:provenance.image_sha256||r.images?.[name]
      };
      const branch=item.source_branch||(inventory[name]?
        "Common source commit (not dedicated)":"—");
      const commit=item.source_commit?
        (item.source_url?'<a target="_blank" rel="noopener noreferrer" href="'+
          esc(item.source_url)+'">'+esc(item.source_commit)+'</a>':
          esc(item.source_commit)):"—";
      return '<tr><th scope="row">'+toolLabelHtml(name)+'</th>'+
        '<td>'+esc(branch)+'</td><td>'+commit+
        '</td><td class="code-hash">'+(esc(item.image_sha256)||"Not recorded")+
        '</td></tr>';
    }).join("")+'</tbody></table></div></section>':
    '<p class="hint">Assembler build details unavailable.</p>';
  el("provenanceContent").innerHTML='<div class="provenance-box"><dl>'+fields.map(([k,v])=>
    '<dt>'+esc(k)+'</dt><dd>'+esc(v)+'</dd>').join("")+
    '</dl></div>'+buildLinks;
}

function drawSubjectControls() {
  const catalog=state.diagnostics?.metric_catalog||{};
  const groups=new Map([
    ["Core measurements",[
      {key:"alignment",label:"Final MiCall alignment",direction:"higher",
        description:"Highest local-alignment score across final MiCall MAX sequences and the specified reference panel; match +1, mismatch −1, gap open −2, gap extension −1."},
      {key:"runtime",label:"MiCall runtime",direction:"lower",
        description:"Lower in-container MiCall monotonic duration in seconds. All reads and downstream processing must be comparable."}
    ]]
  ]);
  for(const [key,definition] of Object.entries(catalog)) {
    const group=definition.stage||"Other diagnostics";
    if(!groups.has(group))groups.set(group,[]);
    groups.get(group).push({key,label:definition.label,
      direction:definition.suggested_direction||"unspecified",
      description:definition.description||"No definition supplied"});
  }
  const chosen=new Map([...el("dominanceSubjects").querySelectorAll("input:checked")]
    .map(node=>[node.value,node.closest(".subject-option")
      .querySelector("select")?.value]));
  el("dominanceSubjects").innerHTML='<legend>Additional dominance requirements</legend>'+[...groups].map(([group,items])=>
    '<div class="subject-group" data-subject-group="'+esc(group)+'">'+
    '<h3>'+esc(group)+'</h3><div class="subject-options">'+
    items.map(subject=>{
      const isCore=subject.key==="alignment"||subject.key==="runtime";
      const dir=chosen.get(subject.key)||subject.direction;
      const checked=chosen.has(subject.key);
      return '<div class="subject-option" data-subject-label="'+
        esc((subject.label+" "+subject.description).toLowerCase())+'">'+
        '<label title="'+esc(subject.description)+'"><input type="checkbox" value="'+
        esc(subject.key)+'"'+(checked?' checked':'')+'>'+
        '<span>'+esc(subject.label)+'</span></label>'+
        (isCore?'<span class="subject-direction">Respectively '+(dir==="higher"?"higher":"lower")+' is better</span>':
        '<select aria-label="Preference for '+esc(subject.label)+'" title="User-selected comparison preference; never a biological proof">'+
        [['unspecified','No direction'],['higher','Higher preferred'],['lower','Lower preferred']].map(([value,label])=>
          '<option value="'+value+'"'+(dir===value?' selected':'')+'>'+label+'</option>').join("")+
        '</select>')+'</div>';
    }).join("")+'</div></div>'
  ).join("");
  el("dominanceSubjects").querySelectorAll("input[type=checkbox]").forEach(node=>
    node.addEventListener("change",()=>{
      drawDominance();drawTable();syncSubjectCount();syncUrl();
    }));
  el("dominanceSubjects").querySelectorAll("select").forEach(node=>
    node.addEventListener("change",()=>{
      drawDominance();drawTable();syncUrl();
    }));
  filterSubjects();
}
function selectedSubjects() {
  const catalog=state.diagnostics?.metric_catalog||{};
  return [...el("dominanceSubjects").querySelectorAll("input:checked")]
    .filter(node=>node.value!==primarySubject().key)
    .map(node=>{
      const key=node.value;
      const core=key==="alignment"||key==="runtime";
      return {key,label:core?(key==="alignment"?"Final MiCall alignment":"MiCall runtime")
        :catalog[key]?.label||key,
        direction:core?(key==="alignment"?"higher":"lower")
          :node.closest(".subject-option").querySelector("select").value};
    });
}
function syncSubjectCount() {
  const total=selectedSubjects().length;
  el("subjectsCount").textContent=total+" additional requirement"+(total===1?"":"s")+" selected";
}
function filterSubjects() {
  const query=el("subjectSearch").value.trim().toLowerCase();
  el("dominanceSubjects").querySelectorAll(".subject-option").forEach(node=>{
    const checkbox=node.querySelector("input");
    checkbox.disabled=checkbox.value===primarySubject().key;
    if(checkbox.disabled)checkbox.checked=false;
    node.hidden=checkbox.disabled||(query!==""&&!node.dataset.subjectLabel.includes(query));
  });
  el("dominanceSubjects").querySelectorAll(".subject-group").forEach(node=>{
    node.hidden=![...node.querySelectorAll(".subject-option")]
      .some(item=>!item.hidden);
  });
  syncSubjectCount();
}
function proofDescription(entry) {
  const observed=entry.observed;
  const partial=observed&&Number.isFinite(observed.mean_delta)
    ? "Observed "+entry.paired+" paired cases: "+
      observed.gains+" gains, "+observed.losses+" losses, "+
      observed.ties+" ties; mean advantage "+
      fmt(observed.mean_delta,6)+". " : "";
  const subset=entry.subset;
  const subsetText=subset?.proof?
    "Observed paired-subset strict all-r Ψ: "+
    (subset.status==="dominates"?"DOMINATES":"DOES NOT DOMINATE")+
    (subset.proof.kind==="exact-single-observation"?
      " (exact one-case sign "+subset.proof.sign+"). ":
      " (Ψ(0) "+fmt(subset.proof.psi0,5)+
      ", Ψ(1) "+fmt(subset.proof.psi1,5)+
      ", Ψ(2) "+fmt(subset.proof.psi2,5)+"). "):
    "No observed-subset proof available. ";
  if(entry.proof) {
    const p=entry.proof;
    return partial+"Independently verified Ψ(0) "+fmt(p.psi0,5)+
      ", Ψ(1) "+fmt(p.psi1,5)+", Ψ(2) "+fmt(p.psi2,5)+
      (p.negative_witness_r===undefined?"":"; counterexample r="+
        fmt(p.negative_witness_r,5));
  }
  return partial+subsetText+
    (entry.reason||"Full-cohort proof unresolved");
}
function syncPsiControls(numeric, additional) {
  el("psiExponent").value=state.psiExponent;
  el("dominanceLegend").hidden=numeric;
  el("momentLegend").hidden=!numeric;
  el("exponentMode").textContent=additional?
    "Matrix: strict all-r dominance with additional requirements. Exponent still controls the case table.":
    state.psiExponent==="all"?"Matrix: strict all-r dominance.":"Matrix and cases: selected Ψ exponent.";
}
function drawDominance() {
  const holder=el("dominanceMatrix"), details=el("dominanceDetails");
  details.classList.add("is-empty");
  const report=state.run.dominance_matrix||{};
  const additional=selectedSubjects();
  const chosen=primarySubject();
  const selected=[chosen,...additional];
  const numeric=state.psiExponent!=="all"&&!additional.length;
  syncSubjectCount();
  syncPsiControls(numeric,additional.length);
  const tools=(Array.isArray(report.tools)&&report.tools.length
    ?report.tools.filter(t=>state.run.tools.includes(t))
    :state.run.tools).filter(t=>state.run.tools.includes(t));
  const matrixTools=tools.length?tools:state.run.tools;
  const snapshot=state.diagnostics?.run_id===state.run.id
    ?state.diagnostics:null;
  const r=numeric?Number(state.psiExponent):null;
  const exponentLabel=r===Infinity?"∞":r;
  const context=numeric
    ?"Ψ("+exponentLabel+") · "+chosen.label+" ("+chosen.direction+"): "+
      (r===0?"mean sign difference (dimensionless)":
       r===1?"mean paired advantage ("+(
         chosen.key==="runtime"?"seconds":chosen.key==="alignment"
           ?"alignment units": "chosen metric units")+")":
       r===Infinity?"eventual sign as r tends to infinity (largest uncancelled absolute paired difference)":
       "mean signed squared advantage (metric units squared)")+
      "."
    :selected.length+" metrics: "+
      selected.map(s=>s.label+" ("+s.direction+")").join("; ")+
      ". Row dominates column when strict Ψ(r)>0 for every real r≥0 "+
      "on all selected metrics; missing measurements remain unresolved.";
  el("dominanceContext").innerHTML=infinityMarkup(esc(context));
  holder.innerHTML='<table class="psi-matrix" style="--matrix-columns:'+matrixTools.length+'"><thead><tr><th>BLUE ↓ / RED →</th>'+
    matrixTools.map(tool=>'<th scope="col">'+toolLabelHtml(tool)+'</th>').join("")+
    '</tr></thead><tbody>'+
    matrixTools.map(a=>'<tr><th scope="row">'+toolLabelHtml(a)+'</th>'+
      matrixTools.map(b=>{
        if(a===b)return '<td class="dom-self">—</td>';
        const result=BenchSubjects.evaluate(report,a,b,selected,snapshot,state.run);
        const verdict=BenchSubjects.observedVerdict(result);
        const evidence=BenchSubjects.evidence(result);
        const reverse=numeric?null:BenchSubjects.observedVerdict(
          BenchSubjects.evaluate(report,b,a,selected,snapshot,state.run));
        const winner=numeric?0:BenchSubjects.winner(verdict,reverse);
        const shortLabel=winner>0?"YES":winner<0||verdict.label==="NO"?"NO":"—";
        const moment=numeric?BenchSubjects.moment(
          result.entries.find(e=>e.key===chosen.key),r,{run:state.run,snapshot,a,b}):null;
        const number=moment?.value;
        const numberClass=number==null?"psi-unavailable":
          number>0?"psi-positive":number<0?"psi-negative":"psi-zero";
        const label=numeric?(number==null?"—":fmtPsi(number)):shortLabel;
        const style=numeric?"psi-number "+numberClass:
          winner>0?"psi-positive":winner<0?"psi-negative":"psi-zero";
        const meaning=numeric?"Ψ("+exponentLabel+") for "+chosen.label+
          ": "+(number==null?"numeric value unavailable":fmtPsi(number))+
          "; "+(moment?.paired||0)+" paired cases":
          (winner>0?a+" dominates "+b:winner<0?b+" dominates "+a:
          verdict.label==="NO"?"Row dominance refuted; column dominance not established":
      "Neither direction demonstrated strict dominance on all selected metrics")+
          " · Row: "+verdict.explanation+" · Column: "+reverse.explanation;
        return '<td class="'+esc(style)+'"><button type="button" data-dominates-a="'+
          esc(a)+'" data-dominates-b="'+esc(b)+'" aria-pressed="'+
          (a===state.firstTool&&b===state.tool)+'" title="'+
          esc(meaning)+(evidence.description?' · Observed: '+
          esc(evidence.description):'')+'" aria-label="'+
          esc(a)+' versus '+esc(b)+': '+esc(meaning)+'"><span class="dom-verdict">'+
          infinityMarkup(esc(label))+'</span></button></td>';
      }).join("")+'</tr>').join("")+'</tbody></table>';
  details.textContent="Select a cell to inspect Ψ values and paired-case evidence.";
  holder.querySelectorAll("button[data-dominates-a]").forEach(button=>{
    button.addEventListener("click",()=>{
      details.classList.remove("is-empty");
      holder.querySelector('[aria-pressed="true"]')?.setAttribute("aria-pressed","false");
      button.setAttribute("aria-pressed","true");
      const a=button.dataset.dominatesA,b=button.dataset.dominatesB;
      const result=BenchSubjects.evaluate(report,a,b,selected,snapshot,state.run);
      const verdict=BenchSubjects.observedVerdict(result);
      const complete=BenchSubjects.verdict(result.status);
      const reverseVerdict=BenchSubjects.observedVerdict(
        BenchSubjects.evaluate(report,b,a,selected,snapshot,state.run));
      const winner=BenchSubjects.winner(verdict,reverseVerdict);
      const numericEntry=numeric?result.entries.find(
        entry=>entry.key===chosen.key):null;
      const number=numeric?BenchSubjects.moment(numericEntry,r,{run:state.run,snapshot,a,b}):null;
      const momentDetails=numeric?'<p>Displayed Ψ('+infinityMarkup(esc(exponentLabel))+') on '+
        esc(chosen.label)+': <strong>'+infinityMarkup(esc(fmtPsi(number.value)))+
        '</strong> · '+number.paired+'/'+number.expected+
        ' paired cases.</p>':'';
      details.innerHTML='<h3>'+toolLabelHtml(a)+' versus '+
        toolLabelHtml(b)+' · '+selected.length+
        ' selected subjects</h3>'+momentDetails+
        (!numeric?'<p>Matrix result: <strong>'+
          esc(winner>0?toolLabel(a)+" dominates":winner<0?toolLabel(b)+" dominates":
            "Neither direction demonstrated dominance")+
          '</strong>. Column evidence: '+esc(reverseVerdict.explanation)+'.</p>':'')+
        '<p>Observed paired-subset dominance (row versus column): <strong>'+
        esc(verdict.label)+'</strong> — '+esc(verdict.explanation)+
        ' · '+esc(verdict.scope)+'. Full-cohort status: <strong>'+
        esc(complete.label)+'</strong>.</p>'+
        '<div class="criterion-results">'+result.entries.map(item=>
          '<article><strong>'+esc(item.label)+'</strong>'+
          '<span>'+esc(item.direction)+" · "+esc(item.status)+
          " · "+item.paired+"/"+item.expected+" samples</span>"+
          '<p>'+esc(proofDescription(item))+'</p></article>').join("")+'</div>'+BenchViews.matrixPlots(
          state.run,state.diagnostics,selected,a,b);
      state.firstTool=a;state.tool=b;
      drawTable();syncUrl();
    });
  });
  const active=[...holder.querySelectorAll("button[data-dominates-a]")].find(
    button=>button.dataset.dominatesA===state.firstTool&&button.dataset.dominatesB===state.tool);
  if(active)active.click();
}

function drawMode() {
  const total=state.mode==="total";
  el("totalPanel").hidden=!total;
  el("pairwisePanel").hidden=total;
  el("totalMode").setAttribute("aria-pressed",String(total));
  el("pairwiseMode").setAttribute("aria-pressed",String(!total));
  el("totalFilter").hidden=!total;
  el("pairwiseFilter").hidden=total;
  if(total)drawCompare();else drawDominance();
  drawTable();
}
function switchMode(mode) {
  if(mode===state.mode||!state.run)return;
  const pinned=el("metricControls").getBoundingClientRect().top<=0;
  state.mode=mode;
  state.sort="id";state.reverse=false;
  el("sampleDialog").close();
  drawMode();syncUrl();
  if(pinned)el("metricWorkspace").scrollIntoView({block:"start"});
}

function render() {
  const run=state.run;
  const roster=Array.isArray(run.tools)?run.tools:[];
  if(!roster.length) {
    el("globalNotice").hidden=false;
    el("globalNotice").textContent="Selected cohort declares no assembler roster.";
    return;
  }
  if(!roster.includes(state.firstTool)||!roster.includes(state.tool)||
      state.firstTool===state.tool){state.firstTool=null;state.tool=null;}
  if(!roster.includes(state.totalTool)){state.totalTool=null;state.distributionTool=null;}
  el("runSelect").value=run.id;
  metricOptions();
  filterSubjects();
  el("outcomeFilter").querySelector('[value="floor"]').disabled=
    state.metric!=="score";
  if(state.metric!=="score"&&el("outcomeFilter").value==="floor")
    el("outcomeFilter").value="all";
  drawOverview();
  drawMode();
  drawDiagnostics();
  drawProvenance();
  syncUrl();
}

/* Cohort rosters are data-defined. Former experimental rows, if present in a
   published run or separate file, are ordinary roster members in that cohort. */

function exportCsv() {
  const info=metricInfo(),r=caseExponent(),total=state.mode==="total";
  if(total?!state.totalTool:!state.firstTool||!state.tool)return;
  const header=total?["alias",state.totalTool+"_"+state.metric,"metric_unit"]:
    ["alias",state.firstTool+"_"+state.metric,state.tool+"_"+state.metric,
      "psi","psi_exponent","metric_unit","numeric_preference"];
  const csv=x=>'"'+String(x??"").replace(/"/g,'""')+'"';
  const rows=[header.map(csv).join(",")].concat(state.rows.map(row=>
    (total?[row.id,row.first,info.unit]:
      [row.id,row.first,row.rival,r==="all"&&row.psi!==null?
      (row.psi>0?"YES":row.psi<0?"NO":"0"):row.psi,state.psiExponent,
      info.unit,state.direction]).map(csv).join(",")));
  const href=URL.createObjectURL(new Blob([rows.join("\n")+"\n"],
    {type:"text/csv"}));
  const link=document.createElement("a");
  link.href=href;
  link.download=state.run.id+"-"+state.metric+(total?"-"+state.totalTool:"-psi-"+state.psiExponent)+".csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}

function bind() {
  el("totalMode").addEventListener("click",()=>switchMode("total"));
  el("pairwiseMode").addEventListener("click",()=>switchMode("pairwise"));
  el("measurementFilter").addEventListener("change",drawTable);
  el("sampleDialogClose").addEventListener("click",()=>el("sampleDialog").close());
  el("distributionClose").addEventListener("click",()=>{
    state.distributionTool=null;
    el("distributionPanel").hidden=true;
  });
  el("runSelect").addEventListener("change",()=>{
    state.run=state.data.runs.find((r)=>r.id===el("runSelect").value);
    state.firstTool=null;state.tool=null;state.totalTool=null;state.distributionTool=null;
    el("search").value="";
    el("outcomeFilter").value="all";
    el("measurementFilter").value="all";
    el("sampleDialog").close();render();
  });
  el("diagnosticMetric").addEventListener("change",()=>{
    state.metric=el("diagnosticMetric").value;
    state.direction=preferredDirection(state.metric);
    state.sort="id";state.reverse=false;
    el("sampleDialog").close();
    render();
  });
  el("singleDirection").addEventListener("change",()=>{
    state.direction=el("singleDirection").value;
    render();
  });
  el("psiExponent").addEventListener("change",()=>{
    state.psiExponent=el("psiExponent").value;
    drawDominance();drawTable();syncUrl();
  });
  el("subjectSearch").addEventListener("input",filterSubjects);
  el("selectSubjects").addEventListener("click",()=>{
    el("dominanceSubjects").querySelectorAll("input[type=checkbox]")
      .forEach(node=>{if(!node.disabled)node.checked=true;});
    drawDominance();drawTable();syncSubjectCount();syncUrl();
  });
  el("clearSubjects").addEventListener("click",()=>{
    el("dominanceSubjects").querySelectorAll("input[type=checkbox]")
      .forEach(node=>{node.checked=false;});
    drawDominance();drawTable();syncSubjectCount();syncUrl();
  });
  el("outcomeFilter").addEventListener("change",drawTable);
  el("search").addEventListener("input",()=>{drawTable();syncUrl();});
  el("exportCsv").addEventListener("click",exportCsv);
  document.querySelectorAll("th button[data-sort]").forEach((button)=>
    button.addEventListener("click",()=>{
      state.reverse=state.sort===button.dataset.sort?!state.reverse:false;
      state.sort=button.dataset.sort;drawTable();
    }));
}

function runOptions() {
  el("runSelect").innerHTML=state.data.runs.map((r)=>
    '<option value="'+esc(r.id)+'">'+
    (r.archive?"Earlier · ":"")+esc(r.title)+'</option>').join("");
  el("runSelect").disabled=false;
}
async function main() {
  bind();
  const bar=el("metricControls"),workspace=el("metricWorkspace");
  const resize=()=>workspace.style.setProperty("--metric-bar-height",bar.getBoundingClientRect().height+"px");
  new ResizeObserver(resize).observe(bar);
  resize();
  try {
    const response=await fetch("./data/runs.json",{cache:"no-store"});
    if(!response.ok)throw new Error("HTTP "+response.status);
    state.data=await response.json();
    const earlier=await fetch("./data/history.json",{cache:"no-store"});
    if(!earlier.ok)throw new Error("Historical runs: HTTP "+earlier.status);
    const history=await earlier.json();
    if(history.schema!=="ivanka.assembler-bench.execution-history.v1"||
       !Array.isArray(history.runs)) {
      throw new Error("Unsupported execution history");
    }
    state.data.runs.push(...history.runs);
    try {
      const diagnosticResponse=await fetch("./data/mapping-diagnostics.json");
      state.diagnostics=diagnosticResponse.ok?await diagnosticResponse.json():null;
    } catch (_) {state.diagnostics=null;}
    if(!Array.isArray(state.data?.runs)||!state.data.runs.length)
      throw new Error("Unsupported or missing public data");
    runOptions();
    const params=new URLSearchParams(location.search);
    const latest=state.data.runs.find(r=>r.cohort==="combined")||
      state.data.runs[0];
    state.run=state.data.runs.find((r)=>r.id===params.get("run"))||latest;
    const requested=params.get("metric")||params.get("diagnostic")||params.get("psi_metric");
    state.metric=requested==="runtime"?"seconds":
      requested==="alignment"||!requested?"score":requested;
    state.direction=["higher","lower"].includes(params.get("order"))
      ?params.get("order"):preferredDirection(state.metric);
    state.mode=params.get("mode")==="pairwise"||(!params.has("mode")&&
      (params.has("first")||params.has("psi_r")||params.has("psi_metric")))?"pairwise":"total";
    state.totalTool=params.get("assembler");
    state.distributionTool=state.totalTool;
    state.firstTool=params.get("first");
    state.tool=params.get("competitor");
    el("search").value=params.get("search")||"";
    state.psiExponent=["all","0","1","2","Infinity"].includes(params.get("psi_r"))
      ?params.get("psi_r"):"1";
    drawSubjectControls();
    const selected=params.get("subjects");
    if(selected!==null) {
      const options=[...el("dominanceSubjects").querySelectorAll("input[type=checkbox]")];
      options.forEach(node=>{node.checked=false;});
      selected.split(",").forEach(token=>{
        const separator=token.lastIndexOf(":");
        if(separator<0)return;
        const key=token.slice(0,separator),direction=token.slice(separator+1);
        if(!["higher","lower","unspecified"].includes(direction))return;
        const node=options.find(item=>item.value===key);
        if(!node)return;
        node.checked=true;
        const dropdown=node.closest(".subject-option").querySelector("select");
        if(dropdown)dropdown.value=direction;
      });
    }
    render();
  } catch(error) {
    el("globalNotice").textContent="Couldn't load the results: "+error.message;
  }
}
main();

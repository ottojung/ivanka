"use strict";
const el = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmt = (x, digits = 2) => Number.isFinite(x)
  ? Number(x).toLocaleString("en", { maximumFractionDigits: digits }) : "—";
const fmtPsi = x => {
  if(!Number.isFinite(x))return "—";
  if(x===0)return "0";
  const abs=Math.abs(x);
  const value=(abs<0.0001||abs>=1000000)
    ?x.toExponential(2).replace("e+","e")
    :x.toLocaleString("en",{maximumSignificantDigits:4});
  return x>0?"+"+value:value;
};
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
const state = {data:null,run:null,metric:"score",firstTool:null,tool:null,
  sort:"id",reverse:false,rows:[],diagnostics:null,
  direction:"higher",psiExponent:"all",psiMetric:"alignment",
  distributionTool:null};

function metricInfo() {
  return BenchRanks.definition(state.metric,state.diagnostics?.metric_catalog);
}
function currentRows() {
  const all=BenchRanks.pairs(state.run,state.diagnostics,state.metric,
    state.direction,state.firstTool,state.tool);
  const query=el("search").value.trim().toLowerCase();
  const outcome=el("outcomeFilter").value;
  const rows=all.filter(row=>{
    if(!row.id.toLowerCase().includes(query) &&
       !(row.detail?.family||"").toLowerCase().includes(query))return false;
    if(outcome==="all")return true;
    if(outcome==="floor")return state.metric==="score" &&
      row.detail?.floor_ok===false;
    return outcome===classify(row);
  });
  rows.sort((a,b)=>{
    const sort=state.sort;
    const value=x=>sort==="id"?x.id:x[sort];
    const left=value(a),right=value(b);
    const cmp=sort==="id"?left.localeCompare(right):
      left===null?right===null?0:1:right===null?-1:left-right;
    return state.reverse?-cmp:cmp;
  });
  state.rows=rows;
  return rows;
}
function classify(row) {
  if(row.unavailable) {
    const failures=row.detail?.failures;
    const affected=Array.isArray(failures)
      ?failures.includes(state.firstTool)||failures.includes(state.tool)
      :failures&&(failures[state.firstTool]>0||failures[state.tool]>0);
    return affected?"failure":"unavailable";
  }
  if(Math.abs(row.delta)<1e-9)return "tie";
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
  if(!BenchRanks.definition(state.metric,catalog))state.metric="score";
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
  params.set("metric",state.metric==="score"?"alignment":
    state.metric==="seconds"?"runtime":state.metric);
  params.set("order",state.direction);
  if(state.firstTool)params.set("first",state.firstTool);
  if(state.tool)params.set("competitor",state.tool);
  if(el("search").value)params.set("search",el("search").value);
  params.set("psi_r",state.psiExponent);
  if(state.psiExponent!=="all")params.set("psi_metric",state.psiMetric);
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
    esc(row.tool)+'" aria-label="Show '+esc(toolLabel(row.tool))+
    ' '+esc(info.label)+' distribution">'+
    '<span class="bar-name">'+row.rank+'. '+
    esc(toolLabel(row.tool))+'</span>'+
    '<span class="bar-track"><span class="bar-fill '+
    (row.tool===state.firstTool?"":"other")+'" style="width:'+
    (row.mean===null?0:100*Math.abs(row.mean)/cap).toFixed(2)+'%"></span></span>'+
    '<span class="bar-value">'+(row.mean===null?"—":fmt(row.mean,5))+'</span>'+
    '<span class="bar-count">'+esc(incomplete)+'</span>'+
    '</button>';
  }).join("")+
    '<p class="plot-caption">Select an assembler to view its distribution.</p>';
  el("comparisonChart").querySelectorAll("button[data-tool]").forEach(button=>
    button.addEventListener("click",()=>{
      state.distributionTool=button.dataset.tool;
      drawDistribution();
    }));
  if(state.distributionTool)drawDistribution();

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
    button=>button.setAttribute("aria-pressed",String(button.dataset.tool===tool)));
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
    ' assemblers have measurements in this run</dd></dl>'+
    (!BenchRanks.isCore(state.metric)?
      '<button type="button" id="addDiagnosticSubject" class="outline-button">'+
      'Include this metric in Ψ subjects</button>':'');
  if(!BenchRanks.isCore(state.metric)) {
    el("addDiagnosticSubject").addEventListener("click",()=>{
      const checkbox=[...el("dominanceSubjects")
        .querySelectorAll('input[type="checkbox"]')]
        .find(node=>node.value===state.metric);
      if(!checkbox)return;
      checkbox.checked=true;
      el("subjectSearch").value="";
      filterSubjects();drawDominance();syncUrl();
      el("dominanceSubjects").scrollIntoView({behavior:"smooth",block:"nearest"});
    });
  }

}

function drawTable() {
  const rows=currentRows();
  const info=metricInfo();
  const suffix=info?.unit==="seconds"?" s":"";
  el("firstColumn").innerHTML=esc(toolLabel(state.firstTool))+' <span>↕</span>';
  el("secondColumn").innerHTML=esc(toolLabel(state.tool))+' <span>↕</span>';
  el("resultRows").innerHTML=rows.map(row=>{
    const outcome=classify(row);
    const tone=outcome==="win"?"positive":
      outcome==="loss"?"negative":"neutral";
    const delta=row.delta!==null?((row.delta>0?"+":"")+
      fmt(row.delta,5)+suffix):"—";
    return '<tr tabindex="0" role="button" data-alias="'+esc(row.id)+
      '" aria-label="Inspect '+esc(row.id)+'">'+
      '<td class="cell-title">'+esc(row.id)+'</td>'+
      '<td class="number">'+fmt(row.first,5)+(row.first===null?"":suffix)+'</td>'+
      '<td class="number">'+fmt(row.rival,5)+(row.rival===null?"":suffix)+'</td>'+
      '<td class="number '+tone+'">'+delta+'</td>'+
      '<td class="'+tone+'">'+esc(outcome)+'</td></tr>';
  }).join("")||'<tr><td colspan="5">No matching measurements.</td></tr>';
  el("resultCount").textContent=rows.length+" visible of "+
    BenchRanks.pairs(state.run,state.diagnostics,state.metric,
      state.direction,state.firstTool,state.tool).length+
    " available case/family records for "+info.label;
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
  const a=state.firstTool,b=state.tool;
  el("sampleDialogTitle").textContent=row.id+" · All recorded metrics";
  const failures=detail?.failures||[];
  const provenance=detail?.family?" · Family: "+detail.family:"";
  const floor=detail?.floor_ok===null||detail?.floor_ok===undefined
    ?"unresolved":detail.floor_ok?"met":"not met";
  el("sampleDialogSummary").textContent=toolLabel(a)+" vs "+
    toolLabel(b)+provenance+" · 90% alignment floor: "+floor+
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
      return '<tr><th scope="row">'+esc(toolLabel(name))+'</th>'+
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
  if(!state.subjectPickerInitialized) {
    chosen.set("alignment","higher");
    chosen.set("runtime","lower");
    state.subjectPickerInitialized=true;
  }
  el("dominanceSubjects").innerHTML='<legend>Dominance subjects</legend>'+[...groups].map(([group,items])=>
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
  // Keep the two independently proven original dimensions as defaults.
  el("dominanceSubjects").querySelectorAll("input[type=checkbox]").forEach(node=>
    node.addEventListener("change",()=>{
      drawDominance();syncSubjectCount();syncUrl();
    }));
  el("dominanceSubjects").querySelectorAll("select").forEach(node=>
    node.addEventListener("change",()=>{
      drawDominance();syncUrl();
    }));
  filterSubjects();
}
function selectedSubjects() {
  const catalog=state.diagnostics?.metric_catalog||{};
  return [...el("dominanceSubjects").querySelectorAll("input:checked")]
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
  el("subjectsCount").textContent=total+" subject"+(total===1?"":"s")+" selected";
}
function filterSubjects() {
  const query=el("subjectSearch").value.trim().toLowerCase();
  el("dominanceSubjects").querySelectorAll(".subject-option").forEach(node=>{
    node.hidden=query!==""&&!node.dataset.subjectLabel.includes(query);
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
function syncPsiControls(selected) {
  const numeric=state.psiExponent!=="all";
  el("psiExponent").value=state.psiExponent;
  el("psiMetricWrap").hidden=!numeric;
  el("dominanceLegend").hidden=numeric;
  el("momentLegend").hidden=!numeric;
  const picker=el("psiMetric");
  if(!selected.some(s=>s.key===state.psiMetric &&
      s.direction!=="unspecified")) {
    state.psiMetric=(selected.find(s=>s.direction!=="unspecified")||{}).key;
  }
  picker.innerHTML=selected.filter(s=>s.direction!=="unspecified")
    .map(s=>'<option value="'+esc(s.key)+'">'+esc(s.label)+'</option>')
    .join("");
  picker.value=state.psiMetric||"";
}
function drawDominance() {
  const holder=el("dominanceMatrix"), details=el("dominanceDetails");
  details.classList.add("is-empty");
  const report=state.run.dominance_matrix||{};
  const selected=selectedSubjects();
  syncSubjectCount();
  syncPsiControls(selected);
  if(!selected.length) {
    holder.innerHTML='<p class="hint">Select at least one checkbox to build an all-subjects dominance relation.</p>';
    details.textContent="The selected subjects form a conjunction: every selected metric must pass its own strict Ψ proof.";return;
  }
  const tools=(Array.isArray(report.tools)&&report.tools.length
    ?report.tools.filter(t=>state.run.tools.includes(t))
    :state.run.tools).filter(t=>state.run.tools.includes(t));
  const matrixTools=tools.length?tools:state.run.tools;
  const snapshot=state.diagnostics?.run_id===state.run.id
    ?state.diagnostics:null;
  const numeric=state.psiExponent!=="all";
  const chosen=selected.find(s=>s.key===state.psiMetric);
  if(numeric&&!chosen) {
    holder.innerHTML='<p class="hint">Choose a metric with a numeric preference to display Ψ advantages.</p>';
    details.textContent="Choose a direction for a selected diagnostic metric.";
    return;
  }
  const r=numeric?Number(state.psiExponent):null;
  el("dominanceContext").textContent=numeric
    ?"Ψ("+r+") · "+chosen.label+" ("+chosen.direction+"): "+
      (r===0?"mean sign difference (dimensionless)":
       r===1?"mean paired advantage ("+(
         chosen.key==="runtime"?"seconds":chosen.key==="alignment"
           ?"alignment units": "chosen metric units")+")":
       "mean signed squared advantage (metric units squared)")+
      "."
    :selected.length+" metrics: "+
      selected.map(s=>s.label+" ("+s.direction+")").join("; ")+
      ". Row dominates column when strict Ψ(r)>0 for every real r≥0 "+
      "on all selected metrics; missing measurements remain unresolved.";
  holder.innerHTML='<table class="psi-matrix" style="--matrix-columns:'+matrixTools.length+'"><thead><tr><th>ROW A ↓ / B →</th>'+
    matrixTools.map(tool=>'<th scope="col">'+esc(toolLabel(tool))+'</th>').join("")+
    '</tr></thead><tbody>'+
    matrixTools.map(a=>'<tr><th scope="row">'+esc(toolLabel(a))+'</th>'+
      matrixTools.map(b=>{
        if(a===b)return '<td class="dom-self">—</td>';
        const result=BenchSubjects.evaluate(report,a,b,selected,snapshot,state.run);
        const verdict=BenchSubjects.observedVerdict(result);
        const evidence=BenchSubjects.evidence(result);
        const shortLabel=
          ["full-yes","observed-yes","partial-yes"].includes(verdict.kind)
          ?(verdict.kind==="full-yes"?verdict.label:"YES")
          :verdict.kind==="observed-no"?"NO":"—";
        const moment=numeric?BenchSubjects.moment(
          result.entries.find(e=>e.key===chosen.key),r):null;
        const number=moment?.value;
        const numberClass=number===null?"psi-unavailable":
          number>0?"psi-positive":number<0?"psi-negative":"psi-zero";
        const label=numeric?(number===null?"—":fmtPsi(number)):shortLabel;
        const style=numeric?"psi-number "+numberClass:
          "dom-"+result.status+" dom-scope-"+verdict.kind;
        const meaning=numeric?"Ψ("+r+") for "+chosen.label+
          ": "+(number===null?"numeric value unavailable":fmtPsi(number))+
          "; "+(moment?.paired||0)+" paired cases":
          "Does "+a+" dominate "+b+" on all "+selected.length+
          " selected metrics? "+verdict.label+" — "+verdict.explanation;
        return '<td class="'+esc(style)+'"><button type="button" data-dominates-a="'+
          esc(a)+'" data-dominates-b="'+esc(b)+'" title="'+
          esc(meaning)+(evidence.description?' · Observed: '+
          esc(evidence.description):'')+'" aria-label="'+
          esc(a)+' versus '+esc(b)+': '+esc(meaning)+'"><span class="dom-verdict">'+
          esc(label)+'</span></button></td>';
      }).join("")+'</tr>').join("")+'</tbody></table>';
  details.textContent="Select a cell to inspect Ψ values and paired-case evidence.";
  holder.querySelectorAll("button[data-dominates-a]").forEach(button=>{
    button.addEventListener("click",()=>{
      details.classList.remove("is-empty");
      const a=button.dataset.dominatesA,b=button.dataset.dominatesB;
      const result=BenchSubjects.evaluate(report,a,b,selected,snapshot,state.run);
      const verdict=BenchSubjects.observedVerdict(result);
      const complete=BenchSubjects.verdict(result.status);
      const numericEntry=numeric?result.entries.find(
        entry=>entry.key===chosen.key):null;
      const number=numeric?BenchSubjects.moment(numericEntry,r):null;
      const momentDetails=numeric?'<p>Displayed Ψ('+r+') on '+
        esc(chosen.label)+': <strong>'+esc(fmtPsi(number.value))+
        '</strong> · '+number.paired+'/'+number.expected+
        ' paired cases.</p>':'';
      details.innerHTML='<h3>'+esc(toolLabel(a))+' versus '+
        esc(toolLabel(b))+' · '+selected.length+
        ' selected subjects</h3>'+momentDetails+
        '<p>Observed paired-subset dominance: <strong>'+
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
      el("firstTool").value=a;
      const choices=state.run.tools.filter(name=>name!==a);
      el("comparisonTool").innerHTML=choices.map(name=>
        '<option value="'+esc(name)+'">'+esc(toolLabel(name))+'</option>').join("");
      el("comparisonTool").value=b;
      el("firstColumn").textContent=toolLabel(a);
      el("secondColumn").textContent=toolLabel(b);
      drawCompare();drawTable();syncUrl();
    });
  });
}

function render() {
  const run=state.run;
  const roster=Array.isArray(run.tools)?run.tools:[];
  if(!roster.length) {
    el("globalNotice").hidden=false;
    el("globalNotice").textContent="Selected cohort declares no assembler roster.";
    return;
  }
  if(!roster.includes(state.firstTool))state.firstTool=roster[0];
  const tools=roster.filter(tool=>tool!==state.firstTool);
  if(!tools.includes(state.tool))state.tool=tools[0]||roster[0];
  el("runSelect").value=run.id;
  el("firstTool").innerHTML=roster.map(tool=>
    '<option value="'+esc(tool)+'">'+esc(toolLabel(tool))+'</option>').join("");
  el("firstTool").value=state.firstTool;
  el("comparisonTool").innerHTML=tools.map(tool=>
    '<option value="'+esc(tool)+'">'+esc(toolLabel(tool))+'</option>').join("");
  if(state.tool)el("comparisonTool").value=state.tool;
  metricOptions();
  el("outcomeFilter").querySelector('[value="floor"]').disabled=
    state.metric!=="score";
  if(state.metric!=="score"&&el("outcomeFilter").value==="floor")
    el("outcomeFilter").value="all";
  drawOverview();
  drawCompare();
  drawDiagnostics();
  drawTable();
  drawDominance();
  drawProvenance();
  syncUrl();
}

/* Cohort rosters are data-defined. Former experimental rows, if present in a
   published run or separate file, are ordinary roster members in that cohort. */

function exportCsv() {
  const info=metricInfo();
  const header=["alias",state.firstTool+"_"+state.metric,
    state.tool+"_"+state.metric,"assembler_a_advantage","outcome",
    "metric_unit","numeric_preference"];
  const csv=x=>'"'+String(x??"").replace(/"/g,'""')+'"';
  const rows=[header.map(csv).join(",")].concat(state.rows.map(row=>
    [row.id,row.first,row.rival,row.delta,classify(row),
      info.unit,state.direction].map(csv).join(",")));
  const href=URL.createObjectURL(new Blob([rows.join("\n")+"\n"],
    {type:"text/csv"}));
  const link=document.createElement("a");
  link.href=href;
  link.download=state.run.id+"-"+state.metric+".csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}

function bind() {
  el("sampleDialogClose").addEventListener("click",()=>el("sampleDialog").close());
  el("distributionClose").addEventListener("click",()=>{
    state.distributionTool=null;
    el("distributionPanel").hidden=true;
  });
  el("runSelect").addEventListener("change",()=>{
    state.run=state.data.runs.find((r)=>r.id===el("runSelect").value);
    state.firstTool=null;state.tool=null;state.distributionTool=null;
    el("search").value="";
    el("outcomeFilter").value="all";
    el("sampleDialog").close();render();
  });
  el("diagnosticMetric").addEventListener("change",()=>{
    state.metric=el("diagnosticMetric").value;
    state.direction=preferredDirection(state.metric);
    state.sort="id";state.reverse=false;state.distributionTool=null;
    el("sampleDialog").close();
    render();
  });
  el("singleDirection").addEventListener("change",()=>{
    state.direction=el("singleDirection").value;
    render();
  });
  el("firstTool").addEventListener("change",()=>{
    state.firstTool=el("firstTool").value;state.tool=null;render();
  });
  el("comparisonTool").addEventListener("change",()=>{
    state.tool=el("comparisonTool").value;render();
  });
  el("psiExponent").addEventListener("change",()=>{
    state.psiExponent=el("psiExponent").value;
    drawDominance();syncUrl();
  });
  el("psiMetric").addEventListener("change",()=>{
    state.psiMetric=el("psiMetric").value;
    drawDominance();syncUrl();
  });
  el("subjectSearch").addEventListener("input",filterSubjects);
  el("selectSubjects").addEventListener("click",()=>{
    el("dominanceSubjects").querySelectorAll("input[type=checkbox]")
      .forEach(node=>{node.checked=true;});
    drawDominance();syncSubjectCount();syncUrl();
  });
  el("clearSubjects").addEventListener("click",()=>{
    el("dominanceSubjects").querySelectorAll("input[type=checkbox]")
      .forEach(node=>{node.checked=false;});
    drawDominance();syncSubjectCount();syncUrl();
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
    const requested=params.get("metric")||params.get("diagnostic");
    state.metric=requested==="runtime"?"seconds":
      requested==="alignment"||!requested?"score":requested;
    state.direction=["higher","lower"].includes(params.get("order"))
      ?params.get("order"):preferredDirection(state.metric);
    state.firstTool=params.get("first");
    state.tool=params.get("competitor");
    el("search").value=params.get("search")||"";
    state.psiExponent=["all","0","1","2"].includes(params.get("psi_r"))
      ?params.get("psi_r"):"all";
    state.psiMetric=params.get("psi_metric")||"alignment";
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

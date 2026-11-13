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
const names = {iva:"IVA",ivanka:"Ivanka",haploflow:"Haploflow",megahit:"MEGAHIT",abyss:"ABySS",spades:"SPAdes",velvet:"Velvet"};
const state = {data:null,run:null,metric:"score",firstTool:null,tool:null,
  sort:"id",reverse:false,rows:[],diagnostics:null,
  direction:"higher",psiExponent:"all",psiMetric:"alignment"};

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

function drawOverview() {
  const progress=state.data.real_progress;
  el("realProgress").textContent=progress
    ?"Physical 198 · current source-attested MiCall attempt: "+
      Object.entries(progress.candidates)
        .sort(([a],[b])=>a==="ivanka"?-1:b==="ivanka"?1:a.localeCompare(b))
        .map(([name,value])=>(names[name]||name)+" "+
          value.finished+"/198 finished"+
          (value.failed?" ("+value.failed+" failed)":"")).join(" · ")+
      "."
    :"Physical sample results are being collected.";
  const run=state.run;
  const expected=run.expected_sample_count;
  const label=run.cohort==="combined"?"Combined · both cohorts":
    run.cohort==="real"?"Physical · MiCall":"HXB2 · MiCall";
  el("runSelect").value=run.id;
  el("runCohort").textContent=label;
  el("runStatus").textContent="In progress";
  el("runStatus").className="status-no";
  el("runDate").textContent=run.date;
  el("runDescription").textContent=run.cohort==="combined"
    ?"Synthetic and real samples, all seven assemblers."
    :run.cohort==="real"?"198 real DNA samples.":"400 synthetic DNA samples.";
  const evidence=run.cohort==="combined"
    ?"400 synthetic + 198 real cases"
    :run.cohort==="real"?"198 physical samples; six rival runs in progress"
    :"400 source-attested HXB2-derived synthetic samples";
  el("globalNotice").textContent="Benchmark in progress · "+evidence+
    ". Comparisons update as more samples finish.";
  const failures=run.samples.reduce((n,s)=>n+s.failures.length,0);
  const floor=run.samples.filter(s=>s.floor_ok===false).length;
  const measured=run.samples.reduce((n,s)=>n+
    Object.values(s.score).filter(Number.isFinite).length,0);
  el("metricCards").innerHTML=card("Cases with results",
    run.sample_count+" / "+expected,"Published samples")+
    card("Assembler results",String(measured),"Of "+(expected*7)+" planned")+
    card("Run failures",String(failures),"MiCall executions")+
    card("Below 90% alignment",String(floor),"Against the strongest rival");
}

function drawCompare() {
  const info=metricInfo();
  const ranking=BenchRanks.summary(state.run,state.diagnostics,
    state.metric,state.direction);
  const valid=ranking.filter(x=>x.mean!==null);
  const cap=Math.max(1e-12,...valid.map(x=>Math.abs(x.mean)));
  const expected=state.run.expected_sample_count||state.run.sample_count;
  const label=state.direction==="lower"?"Lowest first":"Highest first";
  el("comparisonContext").textContent=info.label+" · "+label+
    " · average across measured cases ("+info.unit+").";
  el("comparisonChart").innerHTML=ranking.map(row=>
    '<div class="bar-line"><span class="bar-name">'+row.rank+'. '+
    esc(names[row.tool.toLowerCase()]||row.tool)+'</span>'+
    '<div class="bar-track"><div class="bar-fill '+
    (row.tool===state.firstTool?"":"other")+'" style="width:'+
    (row.mean===null?0:100*Math.abs(row.mean)/cap).toFixed(2)+'%"></div></div>'+
    '<span class="bar-value">'+(row.mean===null?"—":fmt(row.mean,5))+'</span>'+
    '<span class="bar-count">'+row.observed+'/'+expected+' cases</span>'+
    '</div>').join("")+
    '<p class="plot-caption">Average values and sample counts for each assembler.</p>';

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
  el("firstColumn").innerHTML=esc(names[state.firstTool?.toLowerCase()]||
    state.firstTool)+' <span>↕</span>';
  el("secondColumn").innerHTML=esc(names[state.tool?.toLowerCase()]||
    state.tool)+' <span>↕</span>';
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
  const detail=row.detail;
  const info=metricInfo();
  let note="";
  if(state.run.hxb2_truth_verified&&detail) {
    note="HXB2-derived family: "+detail.family+
      ". Failed tool arms: "+(detail.failures?.join(", ")||"none")+".";
  } else if(state.run.cohort==="real"&&detail) {
    note="Source-attested real MiCall sample; 90%-alignment floor: "+
      (detail.floor_ok===null?"unresolved":detail.floor_ok?"met":"not met")+".";
  } else if(detail) {
    note=state.run.cohort==="combined"?
      "Alignment score · "+detail.family:
      "Scores for the selected cases.";
  } else {
    note="Source-attested diagnostic snapshot for one HXB2 case.";
  }
  el("detailPanel").innerHTML='<h3>'+esc(row.id)+' · '+
    esc(info.label)+'</h3><p>'+esc(state.firstTool)+": "+
    fmt(row.first,6)+" "+esc(info.unit)+"; "+esc(state.tool)+": "+
    fmt(row.rival,6)+" "+esc(info.unit)+".</p>"+
    '<p>Numeric A advantage: '+fmt(row.delta,6)+" "+esc(info.unit)+
    ". "+esc(note)+'</p>';
  el("detailPanel").hidden=false;
}

function drawProvenance() {
  const r=state.run;
  const fields=[["Run",r.id],["Source commit",r.source_commit],
    ["Samples",String(r.sample_count)]];
  for(const [label,key] of [["Manifest SHA256","manifest_sha256"],
    ["HXB2 cohort SHA256","cohort_manifest_sha256"],
    ["Benchmark source SHA256","source_manifest_sha256"],
    ["Result SHA256","results_sha256"],
    ["Certificate SHA256","certificate_sha256"],
    ["Diagnostic SHA256","diagnostic_sha256"]]) {
    if(r[key])fields.push([label,r[key]]);
  }
  const inventory=r.micall_fork_provenance?.images;
  const buildLinks=inventory?
    '<section class="dedicated-builds"><h3>Assembler builds</h3>'+
    '<div class="table-scroll provenance-scroll"><table class="dedicated-table"><thead><tr>'+
    '<th>Assembler</th><th>Dedicated fork branch</th>'+
    '<th>Fork source commit</th><th>Immutable image ID</th></tr></thead><tbody>'+
    Object.entries(inventory).map(([name,item])=>
      '<tr><th>'+esc(names[name]||name)+'</th>'+
      '<td>'+esc(item.source_branch||
        "Common source commit (not dedicated)")+'</td>'+
      '<td><a target="_blank" rel="noopener noreferrer" href="'+
        esc(item.source_url)+'">'+esc(item.source_commit)+
      '</a></td><td class="code-hash">'+esc(item.image_sha256)+
      '</td></tr>').join("")+
    '</tbody></table></div></section>':
    '<p class="hint">Assembler build details unavailable.</p>';
  el("provenanceContent").innerHTML='<div class="provenance-box"><dl>'+fields.map(([k,v])=>
    '<dt>'+esc(k)+'</dt><dd>'+esc(v)+'</dd>').join("")+
    '</dl></div>'+buildLinks;
}

function drawSubjectControls() {
  const catalog=state.diagnostics?.metric_catalog||{};
  const groups=new Map([
    ["Qualification",[
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
    return partial+"Independently certified Ψ(0) "+fmt(p.psi0,5)+
      ", Ψ(1) "+fmt(p.psi1,5)+", Ψ(2) "+fmt(p.psi2,5)+
      (p.negative_witness_r===undefined?"":"; counterexample r="+
        fmt(p.negative_witness_r,5));
  }
  return partial+subsetText+
    (entry.reason||"Complete-cohort certification not established");
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
  const report=state.run.dominance_matrix;
  const selected=selectedSubjects();
  syncSubjectCount();
  syncPsiControls(selected);
  if(!report) {
    holder.textContent="No independently certified pairwise Ψ matrix was published.";
    details.textContent="No dominance is inferred from unavailable data.";return;
  }
  if(!selected.length) {
    holder.innerHTML='<p class="hint">Select at least one checkbox to build an all-subjects dominance relation.</p>';
    details.textContent="The selected subjects form a conjunction: every selected metric must pass its own strict Ψ proof.";return;
  }
  const tools=report.tools;
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
      ". Row dominates column when strict Ψ(r)>0 for every r≥0 "+
      "on all selected metrics.";
  holder.innerHTML='<table class="psi-matrix"><thead><tr><th>ROW A ↓ / B →</th>'+
    tools.map(tool=>'<th>'+esc(names[tool.toLowerCase()]||tool)+'</th>').join("")+
    '</tr></thead><tbody>'+
    tools.map(a=>'<tr><th scope="row">'+esc(names[a.toLowerCase()]||a)+'</th>'+
      tools.map(b=>{
        if(a===b)return '<td class="dom-self">—</td>';
        const result=BenchSubjects.evaluate(report,a,b,selected,snapshot);
        const verdict=BenchSubjects.observedVerdict(result);
        const evidence=BenchSubjects.evidence(result);
        const shortLabel=
          ["certified","observed-yes","partial-yes"].includes(verdict.kind)
          ?(verdict.kind==="certified"?verdict.label:"YES")
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
  details.textContent="Select a cell for Ψ values and sample counts. "+
    report.observed_samples+"/"+report.expected_samples+" samples available.";
  holder.querySelectorAll("button[data-dominates-a]").forEach(button=>{
    button.addEventListener("click",()=>{
      details.classList.remove("is-empty");
      const a=button.dataset.dominatesA,b=button.dataset.dominatesB;
      const result=BenchSubjects.evaluate(report,a,b,selected,snapshot);
      const verdict=BenchSubjects.observedVerdict(result);
      const complete=BenchSubjects.verdict(result.status);
      const numericEntry=numeric?result.entries.find(
        entry=>entry.key===chosen.key):null;
      const number=numeric?BenchSubjects.moment(numericEntry,r):null;
      const momentDetails=numeric?'<p>Displayed Ψ('+r+') on '+
        esc(chosen.label)+': <strong>'+esc(fmtPsi(number.value))+
        '</strong> · '+number.paired+'/'+number.expected+
        ' paired cases.</p>':'';
      details.innerHTML='<h3>'+esc(names[a.toLowerCase()]||a)+' versus '+
        esc(names[b.toLowerCase()]||b)+' · '+selected.length+
        ' selected subjects</h3>'+momentDetails+
        '<p>Observed-subset all-r Ψ dominance: <strong>'+
        esc(verdict.label)+'</strong> — '+esc(verdict.explanation)+
        ' · '+esc(verdict.scope)+'. Full-cohort result: <strong>'+
        esc(complete.label)+'</strong>.</p>'+
        '<div class="criterion-results">'+result.entries.map(item=>
          '<article><strong>'+esc(item.label)+'</strong>'+
          '<span>'+esc(item.direction)+" · "+esc(item.status)+
          " · "+item.paired+"/"+item.expected+" samples</span>"+
          '<p>'+esc(proofDescription(item))+'</p></article>').join("")+'</div>';
      state.firstTool=a;state.tool=b;
      el("firstTool").value=a;
      const choices=state.run.tools.filter(name=>name!==a);
      el("comparisonTool").innerHTML=choices.map(name=>
        '<option value="'+esc(name)+'">'+esc(names[name.toLowerCase()]||name)+'</option>').join("");
      el("comparisonTool").value=b;
      el("firstColumn").textContent=a;
      el("secondColumn").textContent=b;
      drawCompare();drawTable();syncUrl();
    });
  });
}

function render() {
  const run=state.run;
  if(!run.tools.includes(state.firstTool))state.firstTool=run.tools[0];
  const tools=run.tools.filter(tool=>tool!==state.firstTool);
  if(!tools.includes(state.tool))state.tool=tools[0];
  el("runSelect").value=run.id;
  el("firstTool").innerHTML=run.tools.map(tool=>
    '<option value="'+esc(tool)+'">'+
    esc(names[tool.toLowerCase()]||tool)+'</option>').join("");
  el("firstTool").value=state.firstTool;
  el("comparisonTool").innerHTML=tools.map(tool=>
    '<option value="'+esc(tool)+'">'+
    esc(names[tool.toLowerCase()]||tool)+'</option>').join("");
  el("comparisonTool").value=state.tool;
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
  el("runSelect").addEventListener("change",()=>{
    state.run=state.data.runs.find((r)=>r.id===el("runSelect").value);
    state.firstTool=null;state.tool=null;el("search").value="";
    el("outcomeFilter").value="all";
    el("detailPanel").hidden=true;render();
  });
  el("diagnosticMetric").addEventListener("change",()=>{
    state.metric=el("diagnosticMetric").value;
    state.direction=preferredDirection(state.metric);
    state.sort="id";state.reverse=false;
    el("detailPanel").hidden=true;
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
    '<option value="'+esc(r.id)+'">'+esc(r.title)+'</option>').join("");
  el("runSelect").disabled=false;
}
async function main() {
  bind();
  try {
    const response=await fetch("./data/runs.json",{cache:"no-store"});
    if(!response.ok)throw new Error("HTTP "+response.status);
    state.data=await response.json();
    try {
      const diagnosticResponse=await fetch("./data/mapping-diagnostics.json");
      state.diagnostics=diagnosticResponse.ok?await diagnosticResponse.json():null;
    } catch (_) {state.diagnostics=null;}
    if(state.data.schema!=="ivanka.assembler-bench.public.v1"||
       !Array.isArray(state.data.runs)||!state.data.runs.length)
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

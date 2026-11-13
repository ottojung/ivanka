"use strict";
const el = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmt = (x, digits = 2) => Number.isFinite(x)
  ? Number(x).toLocaleString("en", { maximumFractionDigits: digits }) : "—";
const names = {iva:"IVA",ivanka:"Ivanka",haploflow:"Haploflow",megahit:"MEGAHIT",abyss:"ABySS",spades:"SPAdes",velvet:"Velvet"};
const state = {data:null,run:null,metric:"score",firstTool:null,tool:null,
  sort:"id",reverse:false,rows:[],diagnostics:null,dedicated:null,
  direction:"higher"};

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
  params.set("subjects",selectedSubjects().map(({key,direction})=>
    key+":"+direction).join(","));
  history.replaceState(null,"","?"+params.toString());
}

function drawOverview() {
  const run=state.run;
  el("runSelect").value=run.id;
  el("runCohort").textContent=run.cohort==="real"?"Real · MiCall":
    run.hxb2_truth_verified?"HXB2 · MiCall":"Synthetic · historical";
  el("runStatus").textContent=run.status==="passed-original-only"
    ?"Original 198 certified":
    run.hxb2_truth_verified?"HXB2 data · partial":"Exploratory · historical";
  el("runStatus").className=run.status==="passed-original-only"?"status-pass":"status-no";
  el("runDate").textContent=run.date;
  el("runDescription").textContent=run.status_reason;
  const coverage=run.hxb2_truth_verified?run.sample_count+"/400 observed HXB2 cases":
    run.cohort==="real"?"198/198 original real cases (IVA comparison only)":
    "Historical random-truth synthetic cases (not eligible)";
  el("globalNotice").textContent=
    "EVIDENCE STATUS · "+coverage+". Full seven-assembler qualification "+
    "has not been established. All available measurements and observed "+
    "comparisons remain visible below; only the separately certified "+
    "original two-assembler result may claim an all-r Ψ pass.";
  if(run.hxb2_truth_verified) {
    const fails=run.samples.reduce((count,s)=>count+s.failures.length,0);
    const floor=run.samples.filter(s=>s.floor_ok===false).length;
    el("metricCards").innerHTML=card("HXB2 cases verified",run.sample_count+" / "+
      run.expected_sample_count,"Real seven-way MiCall pipeline")+
      card("Assembler arms failed",String(fails),"Failures are not Ivanka wins")+
      card("90% floor failures",String(floor),"Only complete seven-arm cases counted")+
      card("Mean comparisons","Available","Measured arms and pairwise counts remain reviewable");
  } else if(run.cohort==="real") {
    const wins=run.samples.filter((s)=>s.seconds.Ivanka<s.seconds.IVA).length;
    el("metricCards").innerHTML=card("Physical MiCall cases","198 / 198","Independently verified original reads")+
      card("Original runtime wins",wins+" / 198","Original Ivanka / IVA qualification")+
      card("Mean time advantage",fmt(run.psi.runtime.psi1)+" s","MiCall monotonic time per sample")+
      card("Alignment Ψ(1)","+"+fmt(run.psi.alignment.psi1,3),"Both all-r gates passed");
  } else {
    const fails=run.families.reduce((total,f)=>total+Object.values(f.failures).reduce((a,b)=>a+b,0),0);
    el("metricCards").innerHTML=card("Legacy cases","400","Disallowed random genomic truth")+
      card("Competitors","7","Exploratory CLI runs only")+
      card("Failed tool runs",String(fails),"Failures are not wins")+
      card("Exploratory comparisons","Available","Only observed values, not certification");
  }
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
    " · ordered observed arithmetic means ("+info.unit+
    "); ties break alphabetically. Each tool uses only its measured cases, "+
    "with counts shown. A numerical rank is not a Ψ-dominance proof.";
  el("comparisonChart").innerHTML=ranking.map(row=>
    '<div class="bar-line"><span class="bar-name">'+row.rank+'. '+
    esc(names[row.tool.toLowerCase()]||row.tool)+'</span>'+
    '<div class="bar-track"><div class="bar-fill '+
    (row.tool===state.firstTool?"":"other")+'" style="width:'+
    (row.mean===null?0:100*Math.abs(row.mean)/cap).toFixed(2)+'%"></div></div>'+
    '<span class="bar-value">'+(row.mean===null?"—":fmt(row.mean,5))+'</span>'+
    '<span class="bar-count">'+row.observed+'/'+expected+' cases</span>'+
    '</div>').join("")+
    '<p class="plot-caption">Measured values only; missing values and failed '+
    'arms are excluded, not replaced with zero. Sort direction is a chosen '+
    'numeric preference, not proof of biological superiority.</p>';
}
function drawDiagnostics() {
  const info=metricInfo();
  const ranking=BenchRanks.summary(state.run,state.diagnostics,
    state.metric,state.direction);
  const expected=state.run.expected_sample_count||state.run.sample_count;
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
  el("diagnosticContext").textContent=
    "Values are ordered by the selected metric, not by a fixed set of clipping "+
    "columns. Measurements from different source stages and incompatible "+
    "cohorts are not combined.";
  el("diagnosticChart").innerHTML=
    '<h3>Measurement coverage</h3>'+
    ranking.map(row=>'<div class="bar-line"><span class="bar-name">'+
      esc(names[row.tool.toLowerCase()]||row.tool)+'</span>'+
      '<div class="bar-track"><div class="bar-fill other" style="width:'+
      (100*row.observed/expected).toFixed(2)+'%"></div></div>'+
      '<span class="bar-value">'+row.observed+'/'+expected+'</span></div>'
    ).join("");
  el("diagnosticMatrix").innerHTML=
    '<table class="diag-table"><thead><tr>'+
    ["Rank","Assembler",info.label+" ("+info.unit+")",
      "Measured cases","Unmeasured cases"].map(text=>
      "<th>"+esc(text)+"</th>").join("")+'</tr></thead><tbody>'+
    ranking.map(row=>'<tr><td>'+row.rank+'</td><th>'+
      esc(names[row.tool.toLowerCase()]||row.tool)+'</th>'+
      '<td>'+ (row.mean===null?"unavailable":fmt(row.mean,6))+
      '</td><td>'+row.observed+'</td><td>'+
      (expected-row.observed)+'</td></tr>').join("")+
    '</tbody></table>';
}

function drawEvidence() {
  const run=state.run;
  if(run.cohort==="real"&&run.status==="passed-original-only") {
    const one=(label,p)=>'<article class="evidence-card"><h3>'+
      esc(label)+'</h3><div class="verdict">Certified strict all-r Ψ</div>'+
      '<p class="hint">'+p.gains+' gains · '+p.losses+' losses · '+
      p.ties+' ties · no nonnegative Ψ zeros.</p>'+
      '<div class="psi-values">'+
      [['Ψ(0)',p.psi0],['Ψ(1)',p.psi1],['Ψ(2)',p.psi2]]
        .map(([name,value])=>'<div><b>'+fmt(value,5)+'</b><span>'+
          esc(name)+'</span></div>').join("")+'</div></article>';
    el("evidenceContent").innerHTML='<div class="evidence-grid">'+
      one("Final MiCall alignment",run.psi.alignment)+
      one("MiCall runtime",run.psi.runtime)+'</div>';
    return;
  }
  const records=[];
  // Even without a complete seven-arm cohort, use each independently
  // measured pair of arms. Do not turn family-level historical averages
  // into supposedly paired read-level measurements.
  if(run.hxb2_truth_verified||run.cohort==="real") {
    for(const a of run.tools)for(const b of run.tools){
      if(a===b)continue;
      const all=BenchRanks.pairs(run,state.diagnostics,state.metric,
        state.direction,a,b);
      const paired=all.filter(row=>row.delta!==null);
      if(!paired.length)continue;
      const deltas=paired.map(row=>row.delta);
      records.push({a,b,paired:paired.length,
        expected:run.expected_sample_count||run.sample_count,
        observed:{gains:deltas.filter(x=>x>0).length,
          losses:deltas.filter(x=>x<0).length,
          ties:deltas.filter(x=>x===0).length,
          mean_delta:deltas.reduce((sum,x)=>sum+x,0)/deltas.length}});
    }
  }
  el("evidenceContent").innerHTML=
    '<p class="hint">Observed pairwise differences for the chosen metric are '+
    'shown where individually verified values exist. These are '+
    'descriptive counts, not mathematical claims of all-r dominance.</p>'+
    (records.length?
      '<div class="table-scroll"><table><thead><tr>'+
      ['Assembler A','Assembler B','Paired cases','A gains','A losses',
        'Ties','Mean A advantage'].map(x=>'<th>'+esc(x)+'</th>').join('')+
      '</tr></thead><tbody>'+records.map(r=>'<tr><td>'+esc(r.a)+
        '</td><td>'+esc(r.b)+'</td><td>'+r.paired+'/'+r.expected+
        '</td><td>'+r.observed.gains+'</td><td>'+r.observed.losses+
        '</td><td>'+r.observed.ties+'</td><td>'+
        fmt(r.observed.mean_delta,5)+'</td></tr>').join("")+
      '</tbody></table></div>':
      '<p class="hint">No valid individual paired cases for this metric. '+
      'Available per-assembler measurements are presented in the ranking above.</p>');
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
    note="Original real MiCall sample; 90%-alignment floor: "+
      (detail.floor_ok?"met":"not met")+".";
  } else if(detail) {
    note="Historical family aggregate across "+detail.sample_count+" cases.";
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
    ["Samples",String(r.sample_count)],["Expanded eligibility",r.eligible_for_expanded?"Eligible":"Not eligible"]];
  for(const [label,key] of [["Manifest SHA256","manifest_sha256"],
    ["HXB2 cohort SHA256","cohort_manifest_sha256"],
    ["Benchmark source manifest SHA256","source_manifest_sha256"],
    ["Result SHA256","results_sha256"],
    ["Independent certificate SHA256","certificate_sha256"],
    ["Diagnostic SHA256","diagnostic_sha256"]]){
    if(r[key])fields.push([label,r[key]]);
  }
  if(r.micall_fork_provenance) {
    fields.push(["MiCall fork build provenance",
      r.micall_fork_provenance.status+": "+r.micall_fork_provenance.message]);
  }
  for(const [tool,ref] of Object.entries(r.images||{})) {
    fields.push([tool+" pinned image",typeof ref==="string"?ref:JSON.stringify(ref)]);
  }
  const inventory=state.dedicated;
  const available=inventory&&inventory.status===
    "SEVEN_INDEPENDENT_BRANCH_IMAGES_VERIFIED";
  const buildLinks=available?
    '<section class="dedicated-builds"><h3>Independently verified dedicated candidate images</h3>'+
    '<p class="hint">These are available branch-specific builds for future '+
    'MiCall runs, <strong>not</strong> the provenance of historical results above. '+
    'No new scientific qualification is implied by an image build.</p>'+
    '<p>Common MiCall baseline: <a href="'+esc(inventory.baseline_url)+
    '" rel="noopener noreferrer" target="_blank">'+
    esc(inventory.baseline_commit.slice(0,12))+'</a></p>'+
    '<div class="table-scroll"><table class="dedicated-table"><thead><tr>'+
    '<th>Assembler</th><th>Dedicated branch</th><th>Fork source commit</th>'+
    '<th>Immutable image ID</th></tr></thead><tbody>'+
    Object.entries(inventory.images).map(([name,item])=>
      '<tr><th>'+esc(names[name]||name)+'</th>'+
      '<td>'+esc(item.source_branch)+'</td>'+
      '<td><a target="_blank" rel="noopener noreferrer" href="'+
        esc(item.source_url)+'">'+esc(item.source_commit.slice(0,12))+
        '</a></td><td class="code-hash" title="'+esc(item.image_sha256)+'">'+
        esc(item.image_sha256.slice(0,20))+'…</td></tr>').join("")+
    '</tbody></table></div></section>':
    '<p class="hint">Dedicated fork branch image attestation unavailable.</p>';
  el("provenanceContent").innerHTML='<div class="provenance-box"><dl>'+fields.map(([k,v])=>
    '<dt>'+esc(k)+'</dt><dd>'+esc(v)+'</dd>').join("")+
    '</dl></div>'+buildLinks;
}

function drawSubjectControls() {
  const catalog=state.diagnostics?.metric_catalog||{};
  const groups=new Map([
    ["Qualification",[
      {key:"alignment",label:"Final MiCall alignment",direction:"higher",
        description:"Higher final MiCall MAX alignment on real samples, or higher known-truth similarity on synthetic samples. Keep those score scales separate."},
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
function drawDominance() {
  const holder=el("dominanceMatrix"), details=el("dominanceDetails");
  details.classList.add("is-empty");
  const report=state.run.dominance_matrix;
  const selected=selectedSubjects();
  syncSubjectCount();
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
  el("dominanceContext").textContent=selected.length+" metrics: "+
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
        const shortLabel=verdict.kind==="certified"?verdict.label:
          verdict.kind==="observed-yes"?"YES":
          verdict.kind==="observed-no"?"NO":
          verdict.kind==="partial-yes"?"PARTIAL":
          verdict.kind==="no-data"?"NO DATA":verdict.label;
        const scope=["observed-yes","observed-no","partial-yes"]
          .includes(verdict.kind)?"obs":"";
        return '<td class="dom-'+esc(result.status)+' dom-scope-'+
          esc(verdict.kind)+'"><button type="button" data-dominates-a="'+
          esc(a)+'" data-dominates-b="'+esc(b)+'" title="'+
          esc(verdict.explanation)+
          (evidence.description?' · Observed: '+esc(evidence.description):'')+
          '" aria-label="Does '+esc(a)+
          ' dominate '+esc(b)+' on all '+selected.length+' selected metrics? '+
          esc(verdict.label)+' — '+esc(verdict.explanation)+
          (evidence.description?'. Observed: '+esc(evidence.description):'')+
          '"><span class="dom-verdict">'+esc(shortLabel)+
          '</span>'+(scope?'<span class="dom-mini">'+esc(scope)+
          '</span>':'')+'</button></td>';
      }).join("")+'</tr>').join("")+'</tbody></table>';
  details.textContent="Select a cell for paired counts, Ψ proofs, "+
    "and metric details. "+report.observed_samples+"/"+report.expected_samples+
    " samples recorded.";
  holder.querySelectorAll("button[data-dominates-a]").forEach(button=>{
    button.addEventListener("click",()=>{
      details.classList.remove("is-empty");
      const a=button.dataset.dominatesA,b=button.dataset.dominatesB;
      const result=BenchSubjects.evaluate(report,a,b,selected,snapshot);
      const verdict=BenchSubjects.observedVerdict(result);
      const complete=BenchSubjects.verdict(result.status);
      details.innerHTML='<h3>'+esc(names[a.toLowerCase()]||a)+' versus '+
        esc(names[b.toLowerCase()]||b)+' · '+selected.length+
        ' selected subjects</h3><p>Observed-subset all-r Ψ dominance: <strong>'+
        esc(verdict.label)+'</strong> — '+esc(verdict.explanation)+
        ' ('+esc(verdict.scope)+'). Full-cohort certified verdict: <strong>'+
        esc(complete.label)+'</strong>. Observed comparisons and their proofs '+
        'are separately itemized below.</p>'+
        '<div class="criterion-results">'+result.entries.map(item=>
          '<article><strong>'+esc(item.label)+'</strong>'+
          '<span>'+esc(item.direction)+" · "+esc(item.status)+
          " · "+item.paired+"/"+item.expected+" samples</span>"+
          '<p>'+esc(proofDescription(item))+'</p></article>').join("")+'</div>'+
        '<p class="hint">A descriptive preference is not proof of biological superiority. '+
        'Unmeasured diagnostics cannot be scored as zero.</p>';
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
  drawEvidence();
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
    try {
      const res=await fetch("./data/dedicated-images.json",{cache:"no-store"});
      state.dedicated=res.ok?await res.json():null;
    } catch (_) {state.dedicated=null;}
    if(state.data.schema!=="ivanka.assembler-bench.public.v1"||
       !Array.isArray(state.data.runs)||!state.data.runs.length)
      throw new Error("Unsupported or missing public data");
    el("runSelect").innerHTML=state.data.runs.map((r)=>
      '<option value="'+esc(r.id)+'">'+esc(r.title)+'</option>').join("");
    el("runSelect").disabled=false;
    const params=new URLSearchParams(location.search);
    state.run=state.data.runs.find((r)=>r.id===params.get("run"))||state.data.runs[0];
    const requested=params.get("metric")||params.get("diagnostic");
    state.metric=requested==="runtime"?"seconds":
      requested==="alignment"||!requested?"score":requested;
    state.direction=["higher","lower"].includes(params.get("order"))
      ?params.get("order"):preferredDirection(state.metric);
    state.firstTool=params.get("first");
    state.tool=params.get("competitor");
    el("search").value=params.get("search")||"";
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
    el("globalNotice").textContent="Results unavailable: "+error.message+
      ". No qualification is claimed.";
  }
}
main();

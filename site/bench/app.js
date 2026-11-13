"use strict";
const el = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmt = (x, digits = 2) => Number.isFinite(x)
  ? Number(x).toLocaleString("en", { maximumFractionDigits: digits }) : "—";
const names = {iva:"IVA",ivanka:"Ivanka",haploflow:"Haploflow",megahit:"MEGAHIT",abyss:"ABySS",spades:"SPAdes",velvet:"Velvet"};
const state = {data:null,run:null,metric:"score",firstTool:null,tool:null,
  sort:"id",reverse:false,rows:[],diagnostics:null};

function currentRows() {
  let result;
  if (state.run.hxb2_truth_verified === true) {
    result = state.run.samples.map((s) => {
      const first=s[state.metric][state.firstTool], rival=s[state.metric][state.tool];
      const failed=s.failures.includes(state.firstTool)||s.failures.includes(state.tool)||
        !Number.isFinite(first)||!Number.isFinite(rival);
      return {id:s.alias,first,rival,
        delta:failed?NaN:(state.metric==="score"?first-rival:rival-first),
        failed,detail:s};
    });
  } else if (state.run.cohort === "real") {
    result = state.run.samples.map((s) => {
      const first=s[state.metric][state.firstTool], rival=s[state.metric][state.tool];
      return {id:s.alias,first,rival,
              delta:state.metric==="score"?first-rival:rival-first,
              failed:s.outcome!=="success",detail:s};
    });
  } else {
    result = state.metric === "seconds" ? [] : state.run.families.map((s) => ({
      id:s.family,first:s.scores[state.firstTool],rival:s.scores[state.tool],
      delta:s.scores[state.firstTool]-s.scores[state.tool],
      failed:s.failures[state.firstTool]>0 || s.failures[state.tool]>0,detail:s
    }));
  }
  const query=el("search").value.trim().toLowerCase(), outcome=el("outcomeFilter").value;
  result = result.filter((r) => (
    r.id.toLowerCase().includes(query) ||
    (r.detail.family||"").toLowerCase().includes(query)
  ) &&
    (outcome === "all" || (outcome === "floor"
      ? r.detail.floor_ok === false : outcome === classify(r))));
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
  if(state.firstTool)params.set("first",state.firstTool);
  if(state.tool)params.set("competitor",state.tool);
  if(el("search").value)params.set("search",el("search").value);
  params.set("subjects",selectedSubjects().map(({key,direction})=>
    key+":"+direction).join(","));
  if(el("diagnosticMetric").value)params.set("diagnostic",el("diagnosticMetric").value);
  history.replaceState(null,"","?"+params.toString());
}

function drawOverview() {
  const run=state.run;
  el("runSelect").value=run.id;
  el("runCohort").textContent=run.cohort==="real"?"Real · MiCall":
    run.hxb2_truth_verified?"HXB2 · MiCall":"Synthetic · historical";
  el("runStatus").textContent=run.status==="passed-original-only"
    ?"Original PASS · expanded incomplete":
    run.hxb2_truth_verified?"HXB2 source verified · NOT QUALIFIED":
    "Ineligible · historical only";
  el("runStatus").className=run.status==="passed-original-only"?"status-pass":"status-no";
  el("runDate").textContent=run.date;
  el("runDescription").textContent=run.status_reason;
  el("globalNotice").textContent=run.hxb2_truth_verified
    ?"Expanded qualification: INCOMPLETE. These are real MiCall measurements from an HXB2-validated cohort, but the full 400-synthetic and 198-real seven-way all-exponent Ψ gates remain unproven."
    :"Expanded qualification: INCOMPLETE. The old random-genome cohort is ineligible under Intent 008. The original 198-real IVA gate separately passed.";
  if(run.hxb2_truth_verified) {
    const fails=run.samples.reduce((count,s)=>count+s.failures.length,0);
    const floor=run.samples.filter(s=>s.floor_ok===false).length;
    el("metricCards").innerHTML=card("HXB2 cases verified",run.sample_count+" / "+
      run.expected_sample_count,"Real seven-way MiCall pipeline")+
      card("Assembler arms failed",String(fails),"Failures are not Ivanka wins")+
      card("90% floor failures",String(floor),"Only complete seven-arm cases counted")+
      card("Expanded Ψ verdict","INCOMPLETE","Original and expanded gates remain binding");
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
      card("Expanded Ψ verdict","NOT PASSED","No qualifying synthetic data");
  }
}

function drawCompare() {
  const run=state.run;
  el("scoreView").classList.toggle("active",state.metric==="score");
  el("timeView").classList.toggle("active",state.metric==="seconds");
  if(run.cohort==="synthetic" &&
      !run.hxb2_truth_verified && state.metric==="seconds") {
    el("comparisonContext").textContent="Historical synthetic runtimes are invalid.";
    el("comparisonChart").innerHTML='<p class="hint">No valid runtime comparison. The exploratory runner included truth-scoring time in reported durations.</p>';
    return;
  }
  const values=run.tools.map((tool)=>{
    let value=0,failures=0;
    if(run.hxb2_truth_verified) {
      const good=run.samples.filter(s=>Number.isFinite(s[state.metric][tool]));
      value=good.length?
        good.reduce((sum,s)=>sum+s[state.metric][tool],0)/good.length:0;
      failures=run.samples.length-good.length;
    } else if(run.cohort==="real") {
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
    '<div class="bar-track"><div class="bar-fill '+(r.tool===state.firstTool?"":"other")+
    '" style="width:'+(r.value*100/largest).toFixed(2)+'%"></div></div>'+
    '<span class="bar-value">'+fmt(r.value,3)+suffix+'</span></div>'+
    (r.failures?'<p class="bar-note">'+r.failures+' tool failures — not a passing comparison</p>':"")
  ).join("")+'<p class="plot-caption">'+(state.metric==="score"
    ?'Real scores: MiCall final MAX points. Synthetic scores: global similarity fraction. Do not pool these scales.'
    :'Mean monotonic MiCall runtime in seconds; lower is better.')+'</p>';
  el("comparisonContext").textContent=run.hxb2_truth_verified
    ?"HXB2 reference-validated MiCall output; partial sample means only, with missing arms explicitly excluded. No all-r Ψ verdict is implied."
    :run.cohort==="real"
    ?"Original 198-sample IVA-only comparison; expanded six-rival real comparison remains incomplete."
    :"Historical known-truth synthetic diagnostics; disallowed genomic-truth cohort.";
}

function drawEvidence() {
  const run=state.run;
  if(run.hxb2_truth_verified) {
    el("evidenceContent").innerHTML='<article class="evidence-card"><h3>HXB2 verified biological source</h3>'+
      '<div class="verdict no">INCOMPLETE · no numerical qualification</div><p class="hint">'+
      run.sample_count+' of 400 synthetic cases have completed the genuine MiCall pipeline. '+
      'Every original genomic truth derives from pinned HXB2/subtype reference ancestry; '+
      'no truth was mounted into an assembler container. The required strict '+
      'alignment and runtime Ψ(r) &gt; 0 for all real r ≥ 0 remain unverified for this '+
      'cohort and for the full seven-way 198-real comparison. Failed arms block acceptance.</p></article>';
    return;
  }
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
      '<td class="number">'+fmt(r.first,3)+suffix+'</td>'+
      '<td class="number">'+fmt(r.rival,3)+suffix+'</td>'+
      '<td class="number '+tone+'">'+(r.delta>0?"+":"")+fmt(r.delta,3)+suffix+'</td>'+
      '<td class="'+tone+'">'+outcome+'</td></tr>';
  }).join("")||'<tr><td colspan="5">No matching cases.</td></tr>';
  el("resultCount").textContent=rows.length+" visible of "+
    (state.run.cohort==="real" || state.run.hxb2_truth_verified
      ?state.run.samples.length:state.run.families.length);
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
  if(state.run.hxb2_truth_verified) {
    detail='<p>HXB2-derived family: '+esc(x.family)+'. Ivanka '+fmt(x.score.ivanka,4)+
      ' global score, '+fmt(x.seconds.ivanka,2)+' MiCall seconds. '+
      esc(names[state.tool]||state.tool)+' '+fmt(x.score[state.tool],4)+
      ' global score, '+fmt(x.seconds[state.tool],2)+' MiCall seconds.</p>'+
      '<p>Failed assembler arms: '+(x.failures.length?esc(x.failures.join(", ")):"none")+
      '. All cases here are still unqualified until the complete seven-way gate passes.</p>';
  } else if(state.run.cohort==="real") {
    detail='<p>'+esc(state.firstTool)+': '+fmt(x.score[state.firstTool],3)+
      ' points, '+fmt(x.seconds[state.firstTool],3)+' s. '+
      esc(state.tool)+': '+fmt(x.score[state.tool],3)+' points, '+
      fmt(x.seconds[state.tool],3)+' s.</p>'+
      '<p>90% floor: '+(x.floor_ok?"PASS":"FAIL")+'. Sample alias is not a source file name or patient identifier.</p>';
  } else {
    detail='<p>Mean across '+x.sample_count+' historical cases. '+
      esc(state.firstTool)+' failures: '+x.failures[state.firstTool]+
      '. '+esc(state.tool)+' failures: '+x.failures[state.tool]+'.</p>';
  }
  el("detailPanel").innerHTML='<h3>'+esc(row.id)+' · '+classify(row)+'</h3>'+detail;
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
  el("provenanceContent").innerHTML='<div class="provenance-box"><dl>'+fields.map(([k,v])=>
    '<dt>'+esc(k)+'</dt><dd>'+esc(v)+'</dd>').join("")+'</dl></div>';
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
  if(entry.reason)return entry.reason;
  const proof=entry.proof;
  if(!proof)return "No verified all-exponent proof for this subject.";
  return "Gains "+proof.gains+", losses "+proof.losses+", ties "+proof.ties+
    "; Ψ(0) "+fmt(proof.psi0,5)+", Ψ(1) "+fmt(proof.psi1,5)+
    ", Ψ(2) "+fmt(proof.psi2,5)+
    (proof.negative_witness_r===undefined?"":"; counterexample r="+
      fmt(proof.negative_witness_r,5));
}
function drawDominance() {
  const holder=el("dominanceMatrix"), details=el("dominanceDetails");
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
  const preview=selected.filter(x=>x.key!=="alignment"&&x.key!=="runtime");
  el("dominanceContext").textContent=selected.length+" subject(s): "+
    selected.map(s=>s.label+" ("+s.direction+")").join("; ")+
    ". "+(preview.length?"Diagnostic Ψ needs paired per-sample measurements across the entire cohort. The published single-case diagnostic snapshot cannot establish dominance. ":"")+
    "A proven counterexample falsifies a conjunction; otherwise incomplete data remain incomplete.";
  holder.innerHTML='<table class="psi-matrix"><thead><tr><th>ROW A ↓ / B →</th>'+
    tools.map(tool=>'<th>'+esc(names[tool.toLowerCase()]||tool)+'</th>').join("")+
    '</tr></thead><tbody>'+
    tools.map(a=>'<tr><th scope="row">'+esc(names[a.toLowerCase()]||a)+'</th>'+
      tools.map(b=>{
        if(a===b)return '<td class="dom-self">—</td>';
        const result=BenchSubjects.evaluate(report,a,b,selected);
        const label={self:"—",none:"SELECT SUBJECTS",dominates:"DOMINATES",
          "does-not-dominate":"NO",incomplete:"INCOMPLETE",
          unresolved:"UNRESOLVED"}[result.status]||"UNVERIFIED";
        return '<td class="dom-'+esc(result.status)+'"><button type="button" data-dominates-a="'+
          esc(a)+'" data-dominates-b="'+esc(b)+'" aria-label="'+esc(a)+
          ' compared with '+esc(b)+' over '+selected.length+' selected subjects: '+
          esc(label)+'">'+esc(label)+'</button></td>';
      }).join("")+'</tr>').join("")+'</tbody></table>';
  details.textContent="Choose a cell to inspect every selected criterion, its "+
    "sample coverage and proof. "+report.observed_samples+" of "+
    report.expected_samples+" samples recorded. No transitivity is assumed.";
  holder.querySelectorAll("button[data-dominates-a]").forEach(button=>{
    button.addEventListener("click",()=>{
      const a=button.dataset.dominatesA,b=button.dataset.dominatesB;
      const result=BenchSubjects.evaluate(report,a,b,selected);
      details.innerHTML='<h3>'+esc(names[a.toLowerCase()]||a)+' versus '+
        esc(names[b.toLowerCase()]||b)+' · '+selected.length+
        ' selected subjects</h3><p>Joint verdict: <b>'+
        esc(result.status)+'</b>. Each criterion uses paired samples '+
        'and its independently certified all-r Ψ result.</p>'+
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

function drawDiagnostics() {
  const data=state.diagnostics;
  const holder=el("diagnosticMatrix"), plot=el("diagnosticChart");
  const dropdown=el("diagnosticMetric");
  const catalog=data?.metric_catalog||{};
  const keys=Object.keys(catalog);
  if(!keys.length) {
    el("diagnosticContext").textContent="No source-verified diagnostic catalog is available.";
    el("diagnosticExplanation").textContent="No metric definition was published.";
    holder.textContent="Metrics unavailable.";plot.replaceChildren();return;
  }
  const prior=dropdown.value||state.requestedDiagnostic;
  if(dropdown.options.length!==keys.length) {
    dropdown.innerHTML=Object.entries(catalog).map(([key,value])=>
      '<option value="'+esc(key)+'">'+esc(value.label)+'</option>').join("");
    dropdown.value=keys.includes(prior)?prior:"soft_clipped_bases_per_1000_read_bases";
  }
  const key=dropdown.value, definition=catalog[key];
  const matchesRun=data.run_id===state.run.id;
  const measured=matchesRun ? data.tools : {};
  const sampleCoverage=matchesRun?data.cases_measured:0;
  const expected=state.run.expected_sample_count||state.run.sample_count;
  const preface=matchesRun?sampleCoverage+" of "+expected+" cases measured":
    "No source-attested diagnostic cases published for this run";
  const preference=definition.suggested_direction==="unspecified"
    ?"No inherent beneficial direction.":(definition.suggested_direction==="higher"
      ?"Higher is conventionally preferred; not necessarily biologically superior."
      :"Lower is conventionally preferred; not necessarily biologically superior.");
  el("diagnosticExplanation").innerHTML=
    '<div class="metric-explanation-head"><h3>'+esc(definition.label)+'</h3>'+
    '<span>'+esc(definition.unit)+'</span></div>'+
    '<p>'+esc(definition.description)+'</p>'+
    '<dl><dt>Measurement stage</dt><dd>'+esc(definition.stage)+'</dd>'+
    '<dt>Units</dt><dd>'+esc(definition.unit)+'</dd>'+
    '<dt>Denominator / basis</dt><dd>'+esc(definition.denominator)+'</dd>'+
    '<dt>Comparison direction</dt><dd>'+esc(preference)+'</dd>'+
    '<dt>Evidence availability</dt><dd>'+esc(preface)+'</dd></dl>'+
    '<button id="addDiagnosticSubject" type="button" class="outline-button">'+
    'Add to Ψ dominance subjects</button>';
  el("addDiagnosticSubject").addEventListener("click",()=>{
    const checkbox=[...el("dominanceSubjects").querySelectorAll("input[type=checkbox]")]
      .find(node=>node.value===key);
    if(!checkbox)return;
    checkbox.checked=true;
    el("subjectSearch").value="";
    filterSubjects();drawDominance();
    syncUrl();
    el("dominanceSubjects").scrollIntoView({behavior:"smooth",block:"nearest"});
  });
  el("diagnosticContext").textContent=
    preface+". This table shows only the chosen "+definition.label+
    " measurement. Values are from the named MiCall stage, not averaged "+
    "across the whole cohort. Missing is not zero, and a single-case "+
    "value cannot prove any all-r Ψ relation.";
  const records=state.run.tools.map(name=>{
    const source=measured[name],value=source?.values?.[key];
    return {name,value:Number.isFinite(value)?value:null,
      source, status:source?.status==="measured"&&Number.isFinite(value)
        ?"Measured":"Unavailable"};
  });
  const valid=records.filter(row=>row.value!==null);
  plot.innerHTML='<h3>'+esc(definition.label)+' <small>('+esc(definition.unit)+')</small></h3>'+
    (valid.length?(()=>{
      const cap=Math.max(...valid.map(item=>item.value),1e-12);
      return records.map(row=>
        '<div class="bar-line"><span class="bar-name">'+
        esc(names[row.name.toLowerCase()]||row.name)+'</span>'+
        '<div class="bar-track"><div class="bar-fill other" style="width:'+
        (row.value===null?0:(100*row.value/cap)).toFixed(3)+'%"></div></div>'+
        '<span class="bar-value">'+(row.value===null?"—":fmt(row.value,4))+
        '</span></div>').join("");
    })():'<p class="hint">No measurements retained for this metric in the selected run.</p>')+
    '<p class="plot-caption">'+esc(sampleCoverage+"/"+expected+
    " evaluated cases; descriptive measurements only. Do not infer all-cohort "+
    "dominance from this snapshot.")+'</p>';
  holder.innerHTML='<table class="diag-table"><thead><tr>'+
    ['Assembler',definition.label+' ('+definition.unit+')',
      'Evidence status','Sample coverage','Measurement stage'].map(x=>
      '<th>'+esc(x)+'</th>').join("")+'</tr></thead><tbody>'+
    records.map(row=>'<tr><th>'+esc(names[row.name.toLowerCase()]||row.name)+
      '</th><td>'+esc(row.value===null?"unavailable":fmt(row.value,6))+
      '</td><td>'+esc(row.status)+'</td><td>'+esc(row.value===null?
      "0 / "+expected:sampleCoverage+" / "+expected)+'</td><td>'+
      esc(row.value===null?"not retained":definition.stage)+'</td></tr>').join("")+
    '</tbody></table>';
}

function render() {
  const run=state.run;
  if(!run.tools.includes(state.firstTool))state.firstTool=run.tools[0];
  const tools=run.tools.filter((t)=>t!==state.firstTool);
  if(!tools.includes(state.tool))state.tool=tools[0];
  el("runSelect").value=run.id;
  el("firstTool").innerHTML=run.tools.map((tool)=>
    '<option value="'+esc(tool)+'">'+esc(names[tool.toLowerCase()]||tool)+'</option>').join("");
  el("firstTool").value=state.firstTool;
  el("comparisonTool").innerHTML=tools.map((tool)=>
    '<option value="'+esc(tool)+'">'+esc(names[tool.toLowerCase()]||tool)+'</option>').join("");
  el("comparisonTool").value=state.tool;
  el("firstColumn").innerHTML=esc(names[state.firstTool.toLowerCase()]||state.firstTool)+' <span>↕</span>';
  el("secondColumn").innerHTML=esc(names[state.tool.toLowerCase()]||state.tool)+' <span>↕</span>';
  drawOverview();drawCompare();drawDominance();drawDiagnostics();
  drawEvidence();drawTable();drawProvenance();syncUrl();
}

function exportCsv() {
  const metric=state.metric==="score"?"alignment":"runtime_seconds";
  const header=["alias",state.firstTool+"_"+metric,state.tool+"_"+metric,
    "assembler_a_advantage","outcome"];
  const values=[header.join(",")].concat(state.rows.map((r)=>
    [r.id,r.first,r.rival,r.delta,classify(r)].join(",")));
  const href=URL.createObjectURL(new Blob([values.join("\n")+"\n"],{type:"text/csv"}));
  const link=document.createElement("a");
  link.href=href;link.download=state.run.id+"-"+metric+".csv";
  document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(href);
}

function bind() {
  el("runSelect").addEventListener("change",()=>{
    state.run=state.data.runs.find((r)=>r.id===el("runSelect").value);
    state.metric="score";state.firstTool=null;state.tool=null;el("search").value="";el("outcomeFilter").value="all";
    el("detailPanel").hidden=true;render();
  });
  for(const [id,metric] of [["scoreView","score"],["timeView","seconds"]]) {
    el(id).addEventListener("click",()=>{
      state.metric=metric;drawCompare();drawTable();syncUrl();
    });
  }
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
  el("diagnosticMetric").addEventListener("change",()=>{
    drawDiagnostics();syncUrl();
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
    if(state.data.schema!=="ivanka.assembler-bench.public.v1"||
       !Array.isArray(state.data.runs)||!state.data.runs.length)
      throw new Error("Unsupported or missing public data");
    el("runSelect").innerHTML=state.data.runs.map((r)=>
      '<option value="'+esc(r.id)+'">'+esc(r.title)+'</option>').join("");
    el("runSelect").disabled=false;
    const params=new URLSearchParams(location.search);
    state.run=state.data.runs.find((r)=>r.id===params.get("run"))||state.data.runs[0];
    state.metric=params.get("metric")==="runtime"?"seconds":"score";
    state.firstTool=params.get("first");
    state.tool=params.get("competitor");
    el("search").value=params.get("search")||"";
    state.requestedDiagnostic=params.get("diagnostic");
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

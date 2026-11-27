"""Checkbox mathematics: every selected metric is an independent obligation."""
import json
import shutil
import subprocess
import unittest

from assembler_bench.site_build import SITE


class CheckboxSelectionTests(unittest.TestCase):
    def _node_current(self, code):
        node=shutil.which("node")
        if node is None:self.skipTest("Node unavailable")
        result=subprocess.run(
            [node,"-e",code,str(SITE/"subjects.js"),
             str(SITE/"data/runs.json")],
            text=True,capture_output=True,check=False,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)


    def test_client_combines_certified_proofs_without_guessing_diagnostics(self):
        self._node_current("""
const assert=require('assert');
const calc=require(process.argv[1]);
const runs=require(process.argv[2]).runs;
const subjects=[
 {key:'alignment',label:'Alignment',direction:'higher'},
 {key:'runtime',label:'Runtime',direction:'lower'}];
const clip={key:'clipped_read_fraction',label:'Clip',direction:'lower'};
for(const run of runs){
 const matrix=run.dominance_matrix;
 assert.equal(matrix.tools.length,run.tools.length);
 for(const a of matrix.tools) for(const b of matrix.tools){
  const v=calc.evaluate(matrix,a,b,subjects);
  assert.equal(v.status,a===b?'self':'incomplete');
 }
 assert.equal(calc.evaluate(matrix,'ivanka','iva',[clip]).status,'incomplete');
 assert.equal(calc.evaluate(matrix,'ivanka','iva',[]).status,'none');
}
console.log('CURRENT_PARTIAL_CONJUNCTION_OK');
""")

    def test_matrix_cells_answer_certified_dominance_not_observed_win_counts(self):
        self._node_current("""
const assert=require('assert');
const calc=require(process.argv[1]);
const runs=require(process.argv[2]).runs;
const alignment=[{key:'alignment',label:'Alignment',direction:'higher'}];
for(const run of runs){
 const report=run.dominance_matrix;
 assert.equal(calc.verdict(calc.evaluate(report,'ivanka','iva',
  alignment).status).label,'?');
 assert.equal(calc.verdict(calc.evaluate(report,'ivanka','ivanka',
  alignment).status).label,'—');
 const verdict=calc.observedVerdict(
   calc.evaluate(report,'ivanka','iva',alignment));
 assert(['YES','NO','—'].includes(verdict.label));
}
assert.equal(calc.verdict('does-not-dominate').label,'NO');
assert.equal(calc.verdict('dominates').label,'YES');
console.log('VERDICTS_STAY_PROVISIONAL');
""")
        js=(SITE/"app.js").read_text()
        html=(SITE/"index.html").read_text()
        matrix=js[js.index("function drawDominance()"):
                  js.index("function render()")]
        self.assertIn("BenchSubjects.verdict(result.status)",matrix)
        self.assertIn("BenchSubjects.evidence(result)",matrix)
        self.assertIn('class="dominance-key"',html)

    def test_inline_evidence_is_visible_but_never_upgrades_partial_psi(self):
        self._node_current("""
const assert=require('assert');
const calc=require(process.argv[1]);
const runs=require(process.argv[2]).runs;
const score={key:'alignment',label:'Alignment',direction:'higher'};
const runtime={key:'runtime',label:'Runtime',direction:'lower'};
for(const run of runs){
 const report=run.dominance_matrix;
 const result=calc.evaluate(report,'ivanka','iva',[score,runtime]);
 assert.equal(result.status,'incomplete');
 const evidence=calc.evidence(result);
 assert(evidence.rows.length<=2);
 if(run.sample_count===0)assert.equal(evidence.rows.length,0);
 assert(evidence.rows.every(x=>x.expected===run.expected_sample_count));
 assert(evidence.rows.every(x=>x.paired<=run.sample_count));
 assert.equal(calc.verdict(result.status).label,'?');
 const uncertain={key:'not_measured',label:'Missing',direction:'higher'};
 assert.equal(calc.evaluate(report,'ivanka','iva',[uncertain]).status,'incomplete');
}
console.log('ACTUAL_PARTIAL_EVIDENCE_VISIBLE');
""")
        js=(SITE/"app.js").read_text()
        self.assertIn("BenchSubjects.evidence(result)",js)
        self.assertIn('class="dom-verdict"',js)

    def test_compact_matrix_preserves_actual_results_without_visual_noise(self):
        js=(SITE/"app.js").read_text()
        css=(SITE/"style.css").read_text()
        html=(SITE/"index.html").read_text()
        matrix=js[js.index("function drawDominance()"):
                  js.index("function render()")]
        self.assertIn('class="dom-verdict"',matrix)
        self.assertNotIn('class="dom-mini"',matrix)
        self.assertIn('esc(label)',matrix)
        self.assertNotIn('esc(scope)',matrix)
        self.assertIn('BenchSubjects.observedVerdict(result)',matrix)
        self.assertIn('evidence.description',matrix)
        self.assertIn('result.entries.map(item=>',matrix)
        self.assertNotIn('class="dom-preview"',matrix)
        self.assertNotIn('class="dom-preview-row"',matrix)
        self.assertNotIn('class="dom-scope-label"',matrix)
        self.assertNotIn('No paired measurements</span>',matrix)
        self.assertIn('class="dominance-key"',html)
        self.assertNotIn('class="dominance-legend"',html)
        self.assertIn('min-width:max(680px,calc(112px + 60px * var(--matrix-columns,7)));width:100%;table-layout:fixed',css)
        self.assertNotIn('min-width:1020px',css)
        self.assertNotIn('min-width:122px',css)
        self.assertNotIn('background:#373025',css)
        self.assertNotIn('background:#40242a',css)
        self.assertNotIn('background:#143728',css)
        self.assertIn('.psi-matrix .dom-scope-observed-no .dom-verdict',css)

    def test_matrix_colours_and_late_coverage_section(self):
        import re
        css=(SITE/"style.css").read_text()
        html=(SITE/"index.html").read_text()
        js=(SITE/"app.js").read_text()
        blue=re.search(r"\.psi-matrix \.dom-scope-observed-yes \.dom-verdict,.*?"
                       r"\.dom-scope-partial-yes \.dom-verdict\{color:var\(--blue\)\}",
                       css,re.S)
        red=re.search(r"\.psi-matrix \.dom-scope-observed-no \.dom-verdict,.*?"
                      r"\.dom-scope-certified\.dom-does-not-dominate \.dom-verdict\{"
                      r"\s*color:var\(--red\)\}",css,re.S)
        self.assertIsNotNone(blue)
        self.assertIsNotNone(red)
        self.assertIn('class="legend-yes"',html)
        self.assertIn('class="legend-no"',html)
        self.assertLess(html.index('class="dominance"'),
                        html.index('class="provenance"'))
        self.assertNotIn('id="diagnosticChart"',html)
        self.assertNotIn('id="diagnosticMatrix"',html)
        self.assertNotIn('id="evidenceContent"',html)
        self.assertNotIn("'<h3>Measurement coverage</h3>'",js)

    def test_numeric_psi_exponents_have_correct_sign_and_mean(self):
        self._node_current("""
const assert=require('assert');
const calc=require(process.argv[1]);
const runs=require(process.argv[2]).runs;
const metric={key:'alignment',label:'Alignment',direction:'higher'};
for(const run of runs){
 const report=run.dominance_matrix;
 const a=calc.evaluate(report,'ivanka','iva',[metric]).entries[0];
 const b=calc.evaluate(report,'iva','ivanka',[metric]).entries[0];
 for(const r of [0,1,2]){
  const x=calc.moment(a,r),y=calc.moment(b,r);
  assert.equal(x.paired,y.paired);
  assert.equal(x.expected,run.expected_sample_count);
  if(x.value!==null && y.value!==null)
    assert(Math.abs(x.value+y.value)<1e-8);
  if(x.paired>0)assert.equal(x.observed,true);
  else assert.equal(x.value,null);
 }
}
const fabricated={paired:2,expected:400,proof:null,
 observed:{gains:1,losses:1,ties:0,mean_delta:1.25}};
assert.equal(calc.moment(fabricated,0).value,0);
assert.equal(calc.moment(fabricated,1).value,1.25);
assert.equal(calc.moment(fabricated,2).value,null);
console.log('PARTIAL_MOMENT_SYMMETRY_OK');
""")
        js=(SITE/"app.js").read_text()
        self.assertIn("const fmtPsi =",js)

    def test_infinity_sign_and_two_direction_winners(self):
        self._node_current("""
const assert=require('assert');
const calc=require(process.argv[1]);
const runs=require(process.argv[2]).runs;
const metric={key:'alignment',label:'Alignment',direction:'higher'};
for(const run of runs){
 for(const a of run.tools)for(const b of run.tools){
  if(a===b)continue;
  const x=calc.evaluate(run.dominance_matrix,a,b,[metric]);
  const y=calc.evaluate(run.dominance_matrix,b,a,[metric]);
  const v=calc.moment(x.entries[0],Infinity).value;
  const w=calc.moment(y.entries[0],Infinity).value;
  if(v!==null&&w!==null)assert(v===-w);
  const vx=calc.observedVerdict(x),vy=calc.observedVerdict(y);
  assert(calc.winner(vx,vy)===-calc.winner(vy,vx));
 }
}
assert.equal(calc.tailSign([10,-10,-3,2]),-1);
assert.equal(calc.tailSign([.8,-.8,.5]),1);
assert.equal(calc.tailSign([3,-3,0]),0);
const entry={paired:1,expected:3,observed:{gains:1,losses:0,ties:0}};
assert.equal(calc.moment(entry,Infinity).value,Infinity);
assert.equal(calc.moment({...entry,observed:{gains:0,losses:1,ties:0}},
 Infinity).value,-Infinity);
assert.equal(calc.moment({...entry,observed:{gains:0,losses:0,ties:1}},
 Infinity).value,0);
assert.equal(calc.moment({...entry,paired:0},Infinity).value,null);
const yes={kind:'observed-yes',label:'YES'},no={kind:'observed-no',label:'NO'};
assert.equal(calc.winner(no,no),0);
assert.equal(calc.winner(yes,no),1);
assert.equal(calc.winner(no,yes),-1);
assert.equal(calc.winner({kind:'partial-yes',label:'YES'},no),0);
""")
        css=(SITE/"style.css").read_text()
        self.assertIn('th[scope="row"]{color:var(--blue)}',css)
        self.assertIn('th[scope="col"]{color:var(--red)}',css)

    def test_individual_cases_use_matrix_colours_and_four_columns(self):
        from html.parser import HTMLParser

        class HeaderParser(HTMLParser):
            in_table = False
            headers = 0
            def handle_starttag(self, tag, attrs):
                if tag == "table" and dict(attrs).get("id") == "resultsTable":
                    self.in_table = True
                if self.in_table and tag == "th":
                    self.headers += 1
            def handle_endtag(self, tag):
                if tag == "table":
                    self.in_table = False

        html=(SITE/"index.html").read_text()
        js=(SITE/"app.js").read_text()
        css=(SITE/"style.css").read_text()
        parser=HeaderParser()
        parser.feed(html)
        self.assertEqual(parser.headers,4)
        self.assertIn('class="assembler-blue">Assembler Blue',html)
        self.assertIn('class="assembler-red">Assembler Red',html)
        self.assertIn('row.psi>0?"assembler-blue"',js)
        self.assertIn('row.psi<0?"assembler-red"',js)
        self.assertIn('colspan="4">',js)
        self.assertIn('psi_exponent',js)
        self.assertNotIn('assembler_a_advantage',js)
        self.assertIn('color:var(--blue)',css)
        self.assertIn('color:var(--red)',css)

    def test_case_psi_transforms_and_shared_direction(self):
        self._node_current("""
const assert=require('assert');
const c=require(process.argv[1]);
for(const [d,expected] of [[5,[1,5,25,Infinity]],[-7,[-1,-7,-49,-Infinity]],[0,[0,0,0,0]],[null,[null,null,null,null]]]){
  assert.deepEqual([0,1,2,Infinity].map(r=>c.casePsi(d,r)),expected);
}
const report={metrics:{alignment:{a:{b:{paired:1,expected:1,proof:{psi1:5}}},b:{a:{paired:1,expected:1,proof:{psi1:-5}}}}}};
assert.equal(c.criterion(report,'a','b','alignment','lower').proof.psi1,-5);
assert.equal(c.criterion(report,'a','b','alignment','higher').proof.psi1,5);
""")
        app=(SITE/"app.js").read_text()
        html=(SITE/"index.html").read_text()
        css=(SITE/"style.css").read_text()
        for removed in ("firstTool","comparisonTool","psiMetric"):
            self.assertNotIn('id="'+removed+'"',html)
        self.assertIn('const numeric=state.psiExponent!=="all"&&!additional.length',app)
        self.assertIn('state.firstTool=a;state.tool=b;',app)
        self.assertIn('position:sticky',css)
        self.assertIn('new ResizeObserver(resize)',app)
        self.assertIn('Ψ(r)',html)

    def test_infinity_glyph_is_unadorned_and_enlarged(self):
        html=(SITE/"index.html").read_text()
        app=(SITE/"app.js").read_text()
        css=(SITE/"style.css").read_text()
        self.assertIn('<option value="Infinity">∞</option>',html)
        self.assertNotIn('∞ (sign)</option>',html)
        self.assertIn('infinityMarkup(esc(label))',app)
        self.assertIn('infinityMarkup(esc(context))',app)
        self.assertIn('infinityMarkup(esc(fmtPsi(number.value)))',app)
        self.assertIn('font-size:1.5em',css)
        self.assertIn('option[value="Infinity"]',css)
        self.assertIn('font-size:22px',css)

    def test_psi_selector_uses_shared_metric_and_is_shareable(self):
        html=(SITE/"index.html").read_text()
        app=(SITE/"app.js").read_text()
        css=(SITE/"style.css").read_text()
        for option in ('all','0','1','2','Infinity'):
            self.assertIn('value="'+option+'"',html)
        self.assertNotIn('id="psiMetric"',html)
        self.assertIn('id="momentLegend"',html)
        self.assertIn('psiExponent:"1"',app)
        self.assertIn('const chosen=primarySubject()',app)
        self.assertIn('params.set("psi_r",state.psiExponent)',app)
        self.assertNotIn('params.set("psi_metric",state.psiMetric)',app)
        self.assertIn('const moment=numeric?BenchSubjects.moment(',app)
        self.assertIn('const moment=numeric?BenchSubjects.moment(',app)
        self.assertIn('.psi-matrix .psi-positive .dom-verdict{color:var(--blue)}',css)
        self.assertIn('.psi-matrix .psi-negative .dom-verdict{color:var(--red)}',css)

    def test_all_hxb2_pairs_have_actual_observed_all_r_psi_results(self):
        self._node_current("""
const assert=require('assert');
const calc=require(process.argv[1]);
const runs=require(process.argv[2]).runs;
const hxb2=runs.find(x=>x.hxb2_truth_verified).dominance_matrix;
const align={key:'alignment',label:'Alignment',direction:'higher'};
const runtime={key:'runtime',label:'Runtime',direction:'lower'};
let count=0;
for(const a of hxb2.tools)for(const b of hxb2.tools){
 if(a===b) continue;
 const x=calc.evaluate(hxb2,a,b,[align,runtime]);
 const verdict=calc.observedVerdict(x);
 assert.equal(x.status,'incomplete');
 assert(x.entries.every(e=>e.paired<=
  runs.find(y=>y.hxb2_truth_verified).sample_count && e.proof===null));
 assert(['YES','NO','—'].includes(verdict.label));
 ++count;
}
assert.equal(count,hxb2.tools.length*(hxb2.tools.length-1));
for(const run of runs.filter(r=>r.cohort!=='synthetic')){
 const result=calc.evaluate(run.dominance_matrix,'ivanka','iva',[align]);
 assert(result.entries[0].paired<=run.sample_count);
 if(run.sample_count===0)assert.equal(result.entries[0].paired,0);
 assert.equal(result.status,'incomplete');
}
console.log('ALL_HXB2_PAIRWISE_COMPARISONS_PARTIAL');
""")

    def test_every_catalog_measurement_can_be_a_checkbox_subject(self):
        snapshot=json.loads((SITE/"data/mapping-diagnostics.json").read_text())
        keys=set(snapshot["metric_catalog"])
        self.assertGreaterEqual(len(keys), 20)
        source=(SITE/"app.js").read_text()
        self.assertIn('Object.entries(catalog)',source)
        self.assertIn('key==="alignment"||key==="runtime"',source)
        self.assertIn('drawSubjectControls();',source)
        self.assertIn('const selected=[chosen,...additional]',source)
        ranks=(SITE/"rankings.js").read_text()
        self.assertIn('snapshot.tools?.[tool]?.values?.[key]',ranks)
        self.assertIn('function summary(',ranks)
        self.assertNotIn('v.soft_clipped_reads,v.soft_clip_events',source)

    def test_current_snapshot_never_invents_missing_diagnostics(self):
        current=json.loads((SITE/"data/mapping-diagnostics.json").read_text())
        self.assertIn(current["cases_measured"],(0,1))
        self.assertEqual(current["expected_cases"],464)
        self.assertEqual(current["status"],"INCOMPLETE")


if __name__=="__main__":
    unittest.main()

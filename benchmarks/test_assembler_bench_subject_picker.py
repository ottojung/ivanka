"""Checkbox mathematics: every selected metric is an independent obligation."""
import json
import shutil
import subprocess
import unittest

from assembler_bench.site_build import SITE


class CheckboxSelectionTests(unittest.TestCase):
    def test_client_combines_certified_proofs_without_guessing_diagnostics(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable for browser-independent JS test")
        code = """
const assert=require('assert');
const calc=require(process.argv[1]);
const runs=require(process.argv[2]).runs;
const real=runs.find(r=>r.cohort==='real').dominance_matrix;
const subjects=[
  {key:'alignment',label:'Alignment',direction:'higher'},
  {key:'runtime',label:'Runtime',direction:'lower'},
];
assert.equal(calc.evaluate(real,'Ivanka','IVA',subjects).status,'dominates');
assert.equal(calc.evaluate(real,'IVA','Ivanka',subjects).status,'does-not-dominate');
assert.equal(calc.evaluate(real,'Ivanka','Ivanka',subjects).status,'self');
assert.equal(calc.evaluate(real,'Ivanka','IVA',[]).status,'none');
const clips={key:'soft_clipped_bases_per_1000_read_bases',
  label:'Soft-clip density',direction:'lower'};
const partial=calc.evaluate(real,'Ivanka','IVA',[clips]);
assert.equal(partial.status,'incomplete');
assert.equal(partial.entries[0].paired,0);
assert.equal(calc.evaluate(real,'Ivanka','IVA',subjects.concat(clips)).status,
  'incomplete');
assert.equal(calc.evaluate(real,'IVA','Ivanka',subjects.concat(clips)).status,
  'does-not-dominate');
const neutral={key:'final_contig_count',label:'Contig count',
  direction:'unspecified'};
assert.equal(calc.evaluate(real,'Ivanka','IVA',[neutral]).status,'unresolved');
const synthetic=runs.find(r=>r.hxb2_truth_verified).dominance_matrix;
assert.equal(calc.evaluate(synthetic,'ivanka','spades',subjects).status,
  'incomplete');
console.log('JS_DIRECTIONS_AND_PARTIAL_EVIDENCE_PASS');
"""
        result = subprocess.run(
            [node, "-e", code, str(SITE/"subjects.js"),
             str(SITE/"data/runs.json")],
            text=True, capture_output=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("JS_DIRECTIONS_AND_PARTIAL_EVIDENCE_PASS", result.stdout)

    def test_matrix_cells_answer_certified_dominance_not_observed_win_counts(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        code = """
const assert=require('assert');
const calc=require(process.argv[1]);
const runs=require(process.argv[2]).runs;
const real=runs.find(r=>r.cohort==='real').dominance_matrix;
const historical=runs.find(r=>r.hxb2_truth_verified).dominance_matrix;
const alignment=[{key:'alignment',direction:'higher',label:'Alignment'}];
const runtime=[{key:'runtime',direction:'lower',label:'Runtime'}];
const diagnostic=[{key:'clipped_read_fraction',direction:'lower',
 label:'Clipped read fraction'}];
const answer=(report,a,b,subjects)=>calc.verdict(
  calc.evaluate(report,a,b,subjects).status).label;
assert.strictEqual(answer(real,'Ivanka','IVA',alignment),'YES');
assert.strictEqual(answer(real,'IVA','Ivanka',alignment),'NO');
assert.strictEqual(answer(real,'Ivanka','IVA',alignment.concat(runtime)),'YES');
assert.strictEqual(answer(real,'IVA','Ivanka',alignment.concat(runtime)),'NO');
assert.strictEqual(answer(real,'Ivanka','Ivanka',alignment),'—');
assert.strictEqual(answer(real,'Ivanka','IVA',[]),'?');
assert.strictEqual(answer(real,'Ivanka','IVA',alignment.concat(diagnostic)),'?');
assert.strictEqual(answer(real,'IVA','Ivanka',alignment.concat(diagnostic)),'NO');
const preview=calc.evaluate(historical,'ivanka','spades',alignment);
assert.strictEqual(preview.status,'incomplete');
assert(preview.entries[0].observed.gains+
  preview.entries[0].observed.losses>0);
assert.strictEqual(calc.verdict(preview.status).label,'?');
assert.strictEqual(calc.verdict('unresolved').label,'?');
assert.strictEqual(calc.verdict('does-not-dominate').label,'NO');
assert.strictEqual(calc.verdict('dominates').label,'YES');
console.log('ALL_PAIRS_ALL_METRICS_MATRIX_VERDICTS_ONLY_PASS');
"""
        result = subprocess.run(
            [node, "-e", code, str(SITE/"subjects.js"),
             str(SITE/"data/runs.json")],
            text=True, capture_output=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ALL_PAIRS_ALL_METRICS_MATRIX_VERDICTS_ONLY_PASS",
                      result.stdout)
        js=(SITE/"app.js").read_text()
        html=(SITE/"index.html").read_text()
        matrix=js[js.index("function drawDominance()"):
                  js.index("function render()")]
        self.assertIn("BenchSubjects.verdict(result.status)",matrix)
        self.assertIn("esc(verdict.label)",matrix)
        self.assertNotIn("cellText(",matrix)
        self.assertNotIn("obs.gains",matrix)
        self.assertIn('class="dominance-key"',html)

    def test_inline_evidence_is_visible_but_never_upgrades_partial_psi(self):
        node=shutil.which("node")
        if node is None:
            self.skipTest("Node unavailable")
        code = """
const assert=require('assert');
const calc=require(process.argv[1]);
const runs=require(process.argv[2]).runs;
const snap=require(process.argv[3]);
const hxb2=runs.find(run=>run.hxb2_truth_verified).dominance_matrix;
const real=runs.find(run=>run.cohort==='real').dominance_matrix;
const metric=(key,direction='higher')=>({key,label:key,direction});
const score=metric('alignment'),runtime=metric('runtime','lower');
const sample=calc.evaluate(hxb2,'ivanka','iva',[score]);
assert.equal(calc.verdict(sample.status).label,'?');
const sampleEvidence=calc.evidence(sample);
assert.equal(sampleEvidence.observedSubjects,1);
assert.equal(sampleEvidence.rows[0].paired,10);
assert.equal(sampleEvidence.rows[0].expected,400);
assert.equal(sampleEvidence.rows[0].gains,10);
assert.equal(sampleEvidence.rows[0].losses,0);
assert(sampleEvidence.rows[0].text.includes('10/400'));
const both=calc.evaluate(hxb2,'ivanka','iva',[score,runtime]);
assert.equal(calc.verdict(both.status).label,'?');
const bothEvidence=calc.evidence(both);
assert.equal(bothEvidence.rows.length,2);
assert.equal(bothEvidence.selectedSubjects,2);
assert.equal(bothEvidence.observedSubjects,2);
assert(bothEvidence.description.includes('alignment:'));
assert(bothEvidence.description.includes('runtime:'));
const diag=metric('soft_clipped_bases_per_1000_read_bases','lower');
const combined=calc.evaluate(hxb2,'ivanka','iva',[score,runtime,diag],snap);
assert.equal(calc.verdict(combined.status).label,'?');
const combinedEvidence=calc.evidence(combined);
assert.equal(combinedEvidence.selectedSubjects,3);
assert.equal(combinedEvidence.rows.length,2);
assert.equal(combinedEvidence.additional,1);
assert(combinedEvidence.description.includes('soft_clipped_bases_per_1000_read_bases'));
const noData=calc.evaluate(real,'Ivanka','IVA',[diag]);
assert.equal(calc.verdict(noData.status).label,'?');
assert.equal(calc.evidence(noData).rows.length,0);
const verified=calc.evaluate(real,'Ivanka','IVA',[score]);
assert.equal(calc.verdict(verified.status).label,'YES');
assert.equal(calc.evidence(verified).rows[0].paired,198);
const falseClaim=calc.evaluate(real,'IVA','Ivanka',[score]);
assert.equal(calc.verdict(falseClaim.status).label,'NO');
assert.equal(calc.evidence(falseClaim).rows[0].paired,198);
const forged={entries:[{key:'x',label:'Fake',paired:2,expected:400,
 observed:{gains:50,losses:0,ties:0}}]};
assert.equal(calc.evidence(forged).rows.length,0);
assert.equal(calc.evidence(both,1).additional,1);
console.log('MATRIX_VERDICT_AND_INLINE_PARTIAL_EVIDENCE_ARE_INDEPENDENT_PASS');
"""
        r=subprocess.run(
            [node,"-e",code,str(SITE/"subjects.js"),
             str(SITE/"data/runs.json"),
             str(SITE/"data/mapping-diagnostics.json")],
            text=True,capture_output=True,timeout=20,check=False)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn(
            "MATRIX_VERDICT_AND_INLINE_PARTIAL_EVIDENCE_ARE_INDEPENDENT_PASS",
            r.stdout)
        js=(SITE/"app.js").read_text()
        matrix=js[js.index("function drawDominance()"):
                  js.index("function render()")]
        self.assertIn("BenchSubjects.evidence(result)",matrix)
        self.assertIn('class="dom-verdict"',matrix)
        self.assertIn('class="dom-mini"',matrix)
        self.assertIn('evidence.description',matrix)
        self.assertIn("esc(verdict.label)",matrix)
        self.assertIn("esc(shortLabel)",matrix)
        self.assertIn("esc(scope)",matrix)
        self.assertNotIn('class="dom-preview"',matrix)
        self.assertNotIn('class="dom-preview-row"',matrix)
        self.assertNotIn('class="dom-scope-label"',matrix)
        self.assertNotIn("esc(item.text)",matrix)

    def test_compact_matrix_preserves_actual_results_without_visual_noise(self):
        js=(SITE/"app.js").read_text()
        css=(SITE/"style.css").read_text()
        html=(SITE/"index.html").read_text()
        matrix=js[js.index("function drawDominance()"):
                  js.index("function render()")]
        self.assertIn('class="dom-verdict"',matrix)
        self.assertIn('class="dom-mini"',matrix)
        self.assertIn('esc(shortLabel)',matrix)
        self.assertIn('esc(scope)',matrix)
        self.assertIn('BenchSubjects.observedVerdict(result)',matrix)
        self.assertIn('evidence.description',matrix)
        self.assertIn('result.entries.map(item=>',matrix)
        self.assertNotIn('class="dom-preview"',matrix)
        self.assertNotIn('class="dom-preview-row"',matrix)
        self.assertNotIn('class="dom-scope-label"',matrix)
        self.assertNotIn('No paired measurements</span>',matrix)
        self.assertIn('class="dominance-key"',html)
        self.assertNotIn('class="dominance-legend"',html)
        self.assertIn('min-width:680px;width:100%;table-layout:fixed',css)
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
                        html.index('class="diagnostics coverage-section"'))
        self.assertLess(html.index('class="evidence"'),
                        html.index('class="diagnostics coverage-section"'))
        self.assertLess(html.index('id="diagnosticChart"'),
                        html.index('class="provenance"'))
        self.assertEqual(html.count('id="diagnosticChart"'),1)
        self.assertNotIn("'<h3>Measurement coverage</h3>'",js)

    def test_all_hxb2_pairs_have_actual_observed_all_r_psi_results(self):
        node=shutil.which("node")
        if not node:self.skipTest("Node unavailable")
        code="""
const assert=require('assert');
const calc=require(process.argv[1]);
const runs=require(process.argv[2]).runs;
const snapshot=require(process.argv[3]);
const hxb2=runs.find(x=>x.hxb2_truth_verified).dominance_matrix;
const real=runs.find(x=>x.cohort==='real').dominance_matrix;
const legacy=runs.find(x=>x.status==='ineligible').dominance_matrix;
const align={key:'alignment',label:'Alignment',direction:'higher'};
const runtime={key:'runtime',label:'Runtime',direction:'lower'};
const diag={key:'soft_clipped_bases_per_1000_read_bases',
  label:'Soft clip density',direction:'lower'};
let count=0;
for(const a of hxb2.tools)for(const b of hxb2.tools){
 if(a===b)continue;
 const x=calc.evaluate(hxb2,a,b,[align,runtime]);
 const v=calc.observedVerdict(x);
 assert(['OBS YES','OBS NO'].includes(v.label),[a,b,v]);
 assert.equal(x.status,'incomplete');
 assert.equal(x.entries.length,2);
 assert(x.entries.every(e=>e.subset?.proof&&e.paired>0));
 assert(x.entries.every(e=>e.proof===null));
 assert(v.scope.includes('2/2 selected subjects'));
 ++count;
}
assert.equal(count,42);
assert.equal(calc.observedVerdict(calc.evaluate(
 hxb2,'ivanka','iva',[align,runtime])).label,'OBS YES');
assert.equal(calc.observedVerdict(calc.evaluate(
 hxb2,'iva','ivanka',[align,runtime])).label,'OBS NO');
assert.equal(calc.observedVerdict(calc.evaluate(
 hxb2,'ivanka','haploflow',[align])).label,'OBS NO');
const composite={...snapshot,cases_measured:2};
const unsupported=calc.evaluate(hxb2,'ivanka','iva',[diag],composite);
assert.equal(calc.observedVerdict(unsupported).label,'NO DATA');
const x=snapshot.tools.ivanka.values[diag.key];
const y=snapshot.tools.iva.values[diag.key];
const diagnosticResult=calc.observedVerdict(
  calc.evaluate(hxb2,'ivanka','iva',[diag],snapshot));
assert.equal(diagnosticResult.label,x<y?'OBS YES':'OBS NO');
assert.equal(calc.observedVerdict(calc.evaluate(
 real,'Ivanka','IVA',[align,runtime])).label,'YES');
assert.equal(calc.observedVerdict(calc.evaluate(
 real,'IVA','Ivanka',[align,runtime])).label,'NO');
assert.equal(calc.observedVerdict(calc.evaluate(
 legacy,'iva','ivanka',[align,runtime])).label,'NO DATA');
assert.equal(calc.observedVerdict(calc.evaluate(
 hxb2,'ivanka','iva',[align,{key:'never_observed',label:'No measurements',
  direction:'higher'}])).label,'PARTIAL YES');
assert.equal(calc.observedVerdict(calc.evaluate(
 hxb2,'ivanka','iva',[{key:'never_observed',label:'None',
  direction:'higher'}])).label,'NO DATA');
assert.equal(calc.observedVerdict(calc.evaluate(
 hxb2,'ivanka','iva',[{key:'final_contig_count',label:'Count',
  direction:'unspecified'}])).label,'UNRESOLVED');
console.log('ALL_42_OBSERVED_HXB2_PAIRWISE_ALL_R_COMPARISONS_DISPLAY_RESULTS');
"""
        r=subprocess.run([node,"-e",code,str(SITE/"subjects.js"),
                          str(SITE/"data/runs.json"),
                          str(SITE/"data/mapping-diagnostics.json")],
                         text=True,capture_output=True,check=False,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('ALL_42_OBSERVED_HXB2_PAIRWISE_ALL_R_COMPARISONS_DISPLAY_RESULTS',
                      r.stdout)

    def test_every_catalog_measurement_can_be_a_checkbox_subject(self):
        snapshot=json.loads((SITE/"data/mapping-diagnostics.json").read_text())
        keys=set(snapshot["metric_catalog"])
        self.assertGreaterEqual(len(keys), 20)
        source=(SITE/"app.js").read_text()
        self.assertIn('Object.entries(catalog)',source)
        self.assertIn('key==="alignment"||key==="runtime"',source)
        self.assertIn('drawSubjectControls();',source)
        self.assertIn('id="addDiagnosticSubject"',source)
        ranks=(SITE/"rankings.js").read_text()
        self.assertIn('snapshot.tools?.[tool]?.values?.[key]',ranks)
        self.assertIn('function summary(',ranks)
        self.assertNotIn('v.soft_clipped_reads,v.soft_clip_events',source)

    def test_current_snapshot_honestly_has_only_one_case(self):
        current=json.loads((SITE/"data/mapping-diagnostics.json").read_text())
        self.assertEqual(current["cases_measured"],1)
        self.assertEqual(current["expected_cases"],400)
        self.assertEqual(current["status"],"INCOMPLETE")


if __name__=="__main__":
    unittest.main()

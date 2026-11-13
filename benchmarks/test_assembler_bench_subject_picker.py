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
        self.assertIn('class="dominance-legend"',html)

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
        self.assertIn('class="dom-preview"',matrix)
        self.assertIn('class="dom-preview-row"',matrix)
        self.assertIn('evidence.additional',matrix)
        self.assertIn('evidence.description',matrix)
        self.assertIn("esc(verdict.label)",matrix)
        self.assertIn("esc(item.text)",matrix)

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

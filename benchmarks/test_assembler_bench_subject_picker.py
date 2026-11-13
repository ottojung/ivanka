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

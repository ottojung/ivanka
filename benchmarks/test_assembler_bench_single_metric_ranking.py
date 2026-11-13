"""Every scientific metric is numerically orderable without inventing values."""
import shutil
import subprocess
import unittest

from assembler_bench.site_build import SITE


class GeneralRankingTests(unittest.TestCase):
    def test_any_metric_and_all_assemblies_are_ranked_from_measured_cases(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node not available")
        code = r"""
const assert=require('assert');
const ranks=require(process.argv[1]);
const runs=require(process.argv[2]).runs;
const diag=require(process.argv[3]);
const real=runs.find(r=>r.cohort==='real');
const historical=runs.find(r=>r.status==='ineligible');
const hxb2=runs.find(r=>r.hxb2_truth_verified);
assert.equal(Object.keys(ranks.CORE).length,2);
assert.equal(Object.keys(diag.metric_catalog).length,23);
assert.equal(ranks.summary(real,diag,'score','higher').length,2);
const realTimes=ranks.summary(real,diag,'seconds','lower');
assert.equal(realTimes[0].tool,'Ivanka');
assert.equal(realTimes[0].observed,198);
const base=ranks.summary(hxb2,diag,'score','higher');
assert.equal(base.length,7);
assert.equal(base[0].observed,10);
assert.equal(base[0].expected,400);
const reverse=ranks.summary(hxb2,diag,'score','lower');
assert.equal(reverse[0].tool,base[base.length-1].tool);
for(const key of Object.keys(diag.metric_catalog)){
  const high=ranks.summary(hxb2,diag,key,'higher');
  const low=ranks.summary(hxb2,diag,key,'lower');
  assert.equal(high.length,7,key);
  assert.equal(low.length,7,key);
  assert(high.every(r=>(r.observed===0||r.observed===1)&&r.expected===400),key);
  assert(high.every(r=>r.observed===0?r.mean===null:Number.isFinite(r.mean)),key);
  assert(high.some(r=>r.observed===1),key);
  assert.equal(ranks.definition(key,diag.metric_catalog).label,
    diag.metric_catalog[key].label);
}
const clip=ranks.summary(real,diag,'soft_clipped_reads','lower');
assert(clip.every(r=>r.mean===null&&r.observed===0));
const partial=ranks.pairs(hxb2,diag,'score','higher','ivanka','spades');
assert.equal(partial.length,10);
assert.equal(partial.filter(x=>!x.unavailable).length,10);
const diagnostic=ranks.pairs(hxb2,diag,'soft_clipped_bases',
  'lower','ivanka','spades');
assert.equal(diagnostic.length,1);
assert.equal(diagnostic[0].id,diag.sample_alias);
assert(!diagnostic[0].unavailable);
assert.equal(ranks.pairs(real,diag,'soft_clipped_bases',
  'lower','Ivanka','IVA').length,0);
const legacy=ranks.summary(historical,diag,'score','higher');
assert(legacy.some(r=>r.observed>0));
assert(ranks.summary(historical,diag,'seconds','lower')
  .every(r=>r.mean===null&&r.observed===0));
console.log('ALL_25_METRIC_NUMERIC_RANKINGS_AND_PARTIAL_CASES_PASS');
"""
        r=subprocess.run([node,"-e",code,str(SITE/"rankings.js"),
                          str(SITE/"data/runs.json"),
                          str(SITE/"data/mapping-diagnostics.json")],
                         capture_output=True,text=True,check=False,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn("ALL_25_METRIC_NUMERIC_RANKINGS_AND_PARTIAL_CASES_PASS",
                      r.stdout)

    def test_total_order_precedes_multimetric_partial_observations(self):
        html=(SITE/"index.html").read_text()
        js=(SITE/"app.js").read_text()
        self.assertLess(html.index('class="compare"'),
                        html.index('class="samples"'))
        self.assertLess(html.index('class="samples"'),
                        html.index('class="dominance"'))
        self.assertIn('id="singleDirection"',html)
        self.assertIn('id="diagnosticMetric"',html)
        self.assertNotIn('id="scoreView"',html)
        self.assertNotIn('id="timeView"',html)
        self.assertIn('BenchRanks.summary(',js)
        self.assertIn('BenchRanks.pairs(',js)
        self.assertIn('BenchSubjects.verdict(result.status)',js)
        self.assertIn('esc(verdict.label)',js)
        self.assertIn('BenchSubjects.evidence(result)',js)
        self.assertNotIn('function cellText(',js)


if __name__=="__main__":
    unittest.main()

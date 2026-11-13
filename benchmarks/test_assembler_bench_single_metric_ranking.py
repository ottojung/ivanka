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
        code = """
const assert=require('assert');
const ranks=require(process.argv[1]);
const runs=require(process.argv[2]).runs;
const diag=require(process.argv[3]);
assert.deepEqual(runs.map(x=>x.cohort),['synthetic','real','combined']);
assert.equal(Object.keys(ranks.CORE).length,2);
assert(Object.keys(diag.metric_catalog).length>=20);
for(const run of runs) {
  const order=ranks.summary(run,diag,'score','higher');
  const times=ranks.summary(run,diag,'seconds','lower');
  assert.equal(order.length,7);
  assert.equal(times.length,7);
  assert(order.every(x=>x.observed<=run.sample_count &&
    x.expected===run.expected_sample_count));
  assert(times.every(x=>x.observed<=run.sample_count));
  const pairs=ranks.pairs(run,diag,'score','higher','ivanka','iva');
  assert.equal(pairs.length,run.sample_count);
  assert(pairs.filter(x=>!x.unavailable).length<=run.sample_count);
  for(const key of Object.keys(diag.metric_catalog)){
    assert.equal(ranks.summary(run,diag,key,'higher').length,7);
    assert.equal(ranks.summary(run,diag,key,'lower').length,7);
    assert.equal(ranks.definition(key,diag.metric_catalog).label,
      diag.metric_catalog[key].label);
  }
}
const real=runs.find(r=>r.cohort==='real');
const combined=runs.find(r=>r.cohort==='combined');
assert(ranks.summary(real,diag,'score','higher')
  .some(x=>x.tool==='ivanka' && x.observed>=0));
assert.equal(combined.sample_count,
  runs[0].sample_count+real.sample_count);
assert(combined.samples.every(s=>Object.values(s.score)
  .filter(Number.isFinite).every(v=>v>=0&&v<=1)));
console.log('ALL_METRIC_SEVEN_WAY_RANKINGS_PASS');
"""
        result=subprocess.run(
            [node,"-e",code,str(SITE/"rankings.js"),
             str(SITE/"data/runs.json"),
             str(SITE/"data/mapping-diagnostics.json")],
            text=True,capture_output=True,check=False,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("ALL_METRIC_SEVEN_WAY_RANKINGS_PASS",result.stdout)

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

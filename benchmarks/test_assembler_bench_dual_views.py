"""Regression coverage for two-assembler distributions and modal metrics."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PairedViewsTests(unittest.TestCase):
    def test_sample_catalog_and_shared_distribution_axes(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        script = r"""
const assert=require('node:assert/strict');
const D=require(process.argv[1]),V=require(process.argv[2]);
const paired=D.compare([2,3,6,9,13],[4,8,10,11]);
assert.equal(paired.first.n,5);
assert.equal(paired.second.n,4);
assert.deepEqual(paired.first.range,paired.second.range);
assert.deepEqual(paired.first.bins.map(b=>b.from),
                 paired.second.bins.map(b=>b.from));
for(const m of [paired.first,paired.second]) {
 const mass=m.bins.reduce((sum,b)=>sum+b.density*(b.to-b.from),0);
 assert(Math.abs(mass-1)<1e-9);
 assert(m.curve.length===161);
}
assert.equal(D.compare([],[]).pooled.n,0);
assert.equal(D.compare([3],[]).second.n,0);
assert.equal(D.compare(Array(7).fill(5),Array(9).fill(5)).pooled.bins.length,1);
const catalog={clips:{label:'Clipped reads',unit:'reads',stage:'Mapping',
 description:'Count CIGAR soft clipping in the sample, not unmapped bases.',
 denominator:'Primary mapped SAM records',suggested_direction:'lower'}};
const samples=[1,2,3,4].map(i=>({
 alias:'R00'+i,failures:i===4?['iva']:[],
 score:{ivanka:20*i,iva:i===4?null:18*i},
 seconds:{ivanka:5+i,iva:i===4?null:6+i},
 diagnostics:{ivanka:{clips:i},iva:{clips:i===2?null:i+3}}
}));
const run={id:'fixture',cohort:'real',tools:['ivanka','iva'],
 hxb2_truth_verified:false,expected_sample_count:4,sample_count:4,samples};
const snapshot={metric_catalog:catalog,run_id:'fixture'};
const groups=V.sampleGroups(run,snapshot,'R002','ivanka','iva');
assert.equal(groups.flatMap(g=>g.rows).length,3);
const clips=groups.flatMap(g=>g.rows).find(r=>r.key==='clips');
assert.equal(clips.first,2);assert.equal(clips.second,null);
const html=V.sampleTable(run,snapshot,'R002','ivanka','iva');
assert(html.includes('Clipped reads')&&html.includes('Primary mapped SAM records'));
assert(html.includes('Ivanka')&&html.includes('IVA'));
assert.equal((html.match(/<summary>/g)||[]).length,3);
assert(html.includes('— means unavailable, not zero'));
const subjects=[
 {key:'alignment',direction:'higher',label:'Alignment'},
 {key:'runtime',direction:'lower',label:'Runtime'},
 {key:'clips',direction:'lower',label:'Clips'}];
const charts=V.matrixPlots(run,snapshot,subjects,'ivanka','iva');
assert.equal((charts.match(/class="matrix-plot"/g)||[]).length,3);
assert.equal((charts.match(/<svg /g)||[]).length,3);
assert.equal((charts.match(/distribution-kde series-a/g)||[]).length,3);
assert.equal((charts.match(/distribution-kde series-b/g)||[]).length,3);
assert(charts.includes('4 measured')&&charts.includes('3 measured'));
assert(charts.includes('2 matched case IDs'));
const missing=V.plotMetric(run,snapshot,{key:'unknown'},'ivanka','iva');
assert(missing.includes('definition unavailable'));
console.log('PAIRED_VIEWS_OK');
"""
        result = subprocess.run(
            [node, "-e", script, str(ROOT / "site/bench/distribution.js"),
             str(ROOT / "site/bench/compare_views.js")],
            capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PAIRED_VIEWS_OK", result.stdout)

    def test_modal_controls_and_no_obsolete_progress(self):
        html = (ROOT / "site/bench/index.html").read_text()
        js = (ROOT / "site/bench/app.js").read_text()
        css = (ROOT / "site/bench/style.css").read_text()
        self.assertIn('<dialog id="sampleDialog"', html)
        self.assertIn('id="sampleDialogClose"', html)
        self.assertNotIn('id="detailPanel"', html)
        self.assertNotIn('id="realProgress"', html)
        self.assertIn('dialog.showModal()', js)
        self.assertIn('BenchViews.sampleTable(', js)
        self.assertIn('BenchViews.matrixPlots(', js)
        self.assertIn('::backdrop', css)


if __name__ == "__main__":
    unittest.main()

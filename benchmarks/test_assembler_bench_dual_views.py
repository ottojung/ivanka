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
assert(html.includes('N/A means unavailable, not zero'));
assert(!html.includes('table-scroll'));
const single=V.sampleTable(run,snapshot,'R002','ivanka',null);
assert(single.includes('Ivanka')&&!single.includes('IVA'));
assert.equal((single.match(/<td class="number">/g)||[]).length,3);
const R=require(require('node:path').join(require('node:path').dirname(process.argv[2]),'rankings.js'));
const cases=R.cases(run,snapshot,'clips','iva');
assert.deepEqual(cases.map(x=>x.first),[4,null,6,null]);
assert.deepEqual(cases.map(x=>x.unavailable),[false,true,false,true]);
assert(cases.every(x=>!Object.hasOwn(x,'delta')));

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
const eachBar=[...charts.matchAll(/<rect class="distribution-bin (series-[ab])" x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)"/g)];
assert(eachBar.length>0&&eachBar.length%2===0);
for(let i=0;i<eachBar.length;i+=2) {
 const behind=eachBar[i],front=eachBar[i+1];
 assert.notEqual(behind[1],front[1]);
 assert.equal(behind[2],front[2],'bars must share x-position');
 assert.equal(behind[4],front[4],'bars must share width');
 assert(Number(behind[5])>=Number(front[5]),'taller bar must render first');
}
const onlyOne=JSON.parse(JSON.stringify(run));
for(const sample of onlyOne.samples)sample.diagnostics.iva.clips=null;
const onePlot=V.plotMetric(onlyOne,snapshot,subjects[2],'ivanka','iva');
assert(onePlot.includes('0 measured'));
assert(onePlot.includes('distribution-bin series-a'));
assert(!onePlot.includes('NaN'));
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

    def test_plain_unavailable_legend_and_na_zero_distinction(self):
        """The unavailability legend stays plain and N/A is never a zero.

        A missing measurement is displayed as ``N/A`` and a measured zero as
        ``0``. The legend must remain a plain sentence so the distinction is
        readable without markup, and must not fall back to the old em dash.
        """
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        script = r"""
const assert=require('node:assert/strict');
const D=require(process.argv[1]),V=require(process.argv[2]);
const catalog={clips:{label:'Clipped reads',unit:'reads',stage:'Mapping',
 description:'Count CIGAR soft clipping in the sample, not unmapped bases.',
 denominator:'Primary mapped SAM records',suggested_direction:'lower'}};
const samples=[1,2].map(i=>({
 alias:'R00'+i,failures:[],
 score:{ivanka:10*i,iva:i===1?0:18*i},
 seconds:{ivanka:5+i,iva:6+i},
 diagnostics:{ivanka:{clips:0},iva:{clips:i===1?null:i+3}}
}));
const run={id:'fixture',cohort:'real',tools:['ivanka','iva'],
 hxb2_truth_verified:false,expected_sample_count:2,sample_count:2,samples};
const snapshot={metric_catalog:catalog,run_id:'fixture'};
const html=V.sampleTable(run,snapshot,'R001','ivanka','iva');
const legend=html.match(/<p class="subtle">([^<]*)<\/p>/);
assert(legend,'plain legend paragraph is missing');
assert.equal(legend[1],
  '3 of 3 metrics have at least one recorded value. N/A means unavailable, not zero.');
const cells=[...html.matchAll(/<td class="number">([^<]*)<\/td>/g)]
  .map(m=>m[1]);
assert.deepEqual(cells,['10','0','6','7','0','N/A'],cells);
assert(cells.includes('0'),'a measured zero must stay visible as 0');
assert(cells.includes('N/A'),'a missing value must be shown as N/A');
assert(!cells.includes('—'),'missing value must not use the old em dash');
assert(!html.includes('— means unavailable'),'stale legend wording returned');
console.log('PLAIN_NA_LEGEND_OK');
"""
        result = subprocess.run(
            [node, "-e", script, str(ROOT / "site/bench/distribution.js"),
             str(ROOT / "site/bench/compare_views.js")],
            capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PLAIN_NA_LEGEND_OK", result.stdout)

    def test_comparison_modes_have_exclusive_controls(self):
        html = (ROOT / "site/bench/index.html").read_text()
        js = (ROOT / "site/bench/app.js").read_text()
        self.assertIn('id="totalMode"', html)
        self.assertIn('id="pairwiseMode"', html)
        self.assertIn('<details class="subject-panel" id="additionalRequirements">', html)
        self.assertIn('el("totalPanel").hidden=!total', js)
        self.assertIn('el("pairwisePanel").hidden=total', js)
        self.assertIn('el("psiCaseHeading").hidden=total', js)
        self.assertIn('el("redCaseHeading").hidden=total', js)
        self.assertIn('params.set("mode",state.mode)', js)
        self.assertIn('state.totalTool=button.dataset.tool', js)
        self.assertIn('if(total)drawCompare();else drawDominance()', js)

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
        self.assertIn('overflow:hidden}', css)
        self.assertIn('overflow-y:auto;overflow-x:hidden', css)
        self.assertIn('.sample-metric-table{min-width:0;width:100%', css)


if __name__ == "__main__":
    unittest.main()

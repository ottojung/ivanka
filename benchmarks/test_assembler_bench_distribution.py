"""Check normalized histogram, Gaussian KDE, and end-user chart controls."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    def test_histogram_density_kde_and_edge_cases(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node is unavailable")
        code = r"""
const assert=require('node:assert/strict');
const D=require(process.argv[1]);
let result=D.model([]);
assert.equal(result.n,0);assert.equal(result.curve.length,0);
result=D.model([72]);
assert.equal(result.n,1);assert.equal(result.bins[0].count,1);
assert.equal(result.curve.length,0);
result=D.model(Array(20).fill(42));
assert.equal(result.n,20);assert.equal(result.bins[0].count,20);
assert.equal(result.curve.length,0);
result=D.model([1,2,4,5,6,8,10,12,15,16,19,24,27,30]);
assert.equal(result.n,14);assert.equal(result.curve.length,161);
assert(result.bandwidth>0);
assert.equal(result.bins.reduce((s,b)=>s+b.count,0),result.n);
const histMass=result.bins.reduce((s,b)=>s+b.density*(b.to-b.from),0);
assert(Math.abs(histMass-1)<1e-9);
const kdeMass=result.curve.slice(1).reduce((sum,p,i)=>{
 const prev=result.curve[i];
 return sum+(p.y+prev.y)/2*(p.x-prev.x);
},0);
assert(kdeMass>.96&&kdeMass<=1.005,kdeMass);
assert(D.model([3,5,Infinity,NaN]).n===2);
assert(D.model([-10,-3,-2,1]).n===4);
const huge=D.model([1e8,1e8+3,1e8+5,1e8+10]);
assert(huge.curve.every(p=>Number.isFinite(p.y)));
console.log('HISTOGRAM_KDE_STATS_VALID');
"""
        test=subprocess.run([node,"-e",code,str(ROOT/"site/bench/distribution.js")],
                            capture_output=True,text=True,timeout=12)
        self.assertEqual(test.returncode,0,test.stderr)
        self.assertIn("HISTOGRAM_KDE_STATS_VALID",test.stdout)

    def test_clickable_chart_no_external_scripts(self):
        html=(ROOT/"site/bench/index.html").read_text()
        js=(ROOT/"site/bench/app.js").read_text()
        self.assertIn('src="./distribution.js"',html)
        self.assertIn('id="distributionChart"',html)
        self.assertIn('id="distributionClose"',html)
        self.assertIn('button type="button" class="bar-line rank-trigger"',js)
        self.assertIn('button.addEventListener("click",()=>{',js)
        self.assertIn('aria-pressed',js)
        self.assertIn("BenchDistribution.model(values)",js)
        self.assertIn("Gaussian KDE",js)
        self.assertNotIn("cdn.",html)

"""The scientific overview never becomes an assembler execution dashboard."""
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

from benchmarks.assembler_bench import workload_activity as activity


ROOT=Path(__file__).resolve().parents[1]


class ResultsFirstOverviewTests(unittest.TestCase):
    def test_static_ui_uses_scientific_summary_and_one_small_notice(self):
        site=ROOT/"site/bench"
        markup=(site/"index.html").read_text()
        script=(site/"app.js").read_text()
        self.assertIn("BenchOverview.summary(",script)
        self.assertIn("BenchOverview.notice(",script)
        self.assertIn("BenchOverview.coverage(",script)
        self.assertIn('src="./overview.js"',markup)
        self.assertNotIn('id="toolProgress"',markup)
        self.assertNotIn("Completed MiCall arms",script)
        self.assertNotIn("Cases with results",script)
        self.assertNotIn("run.status_reason",script)
        self.assertNotIn("comparatorProgress",markup)

    @unittest.skipUnless(shutil.which("node"),"Node.js not installed")
    def test_complete_and_partial_browser_models(self):
        script=r'''
const assert=require("node:assert/strict");
global.BenchRanks=require("./site/bench/rankings.js");
const b=require("./site/bench/overview.js");
const tools=["iva","megahit","ivanka"];
function run(cohort,expected,counts,rows) {
  return {cohort,expected_sample_count:expected,sample_count:rows.length,
    tools,tool_progress:Object.fromEntries(tools.map(t=>[t,
      {expected,finished:counts[t],failed:0}])),
    hxb2_truth_verified:cohort==="synthetic",
    samples:rows};
}
const row={alias:"H001",score:{iva:10,megahit:8,ivanka:null},
  seconds:{iva:4,megahit:6,ivanka:null},failures:[]};
const one=run("synthetic",2,{iva:2,megahit:1,ivanka:0},[row]);
const stats=b.summary(one,null);
assert.equal(stats.alignmentLeader.tool,"iva");
assert.equal(stats.runtimeLeader.tool,"iva");
assert.equal(stats.medianAlignment,9);
assert.equal(stats.medianRuntime,5);
assert.equal(b.coverage(one,"iva",1),"");
assert.equal(b.coverage(one,"megahit",1),"1/2 cases");
const real=run("real",2,{iva:1,megahit:0,ivanka:0},[]);
const report={runs:[real,one],workload:{status:"observed",
  order:["real","synthetic"],running:{real:["iva"],synthetic:[]},
  deferred:["ivanka"]}};
const note=b.notice(report,real);
assert.match(note,/Running: Physical IVA \(1\/2\)/);
assert.match(note,/Awaiting physical: MEGAHIT/);
assert.match(note,/Synthetic measurements follow the earlier cohort/);
assert.match(note,/Deferred: Ivanka/);
assert.doesNotMatch(note,/2\/2/);
const all=run("real",2,{iva:2,megahit:2,ivanka:2},[]);
const allS=run("synthetic",2,{iva:2,megahit:2,ivanka:2},[]);
assert.equal(b.notice({runs:[all,allS]},all),null);
assert.equal(b.notice(report,{...real,archive:{}}),null);
const after=run("real",2,{iva:2,megahit:0,ivanka:0},[]);
const again=b.notice({...report,runs:[after,one],
  workload:{...report.workload,running:{real:["megahit"],synthetic:[]}}},after);
assert.doesNotMatch(again,/IVA \(2\/2\)/);
assert.match(again,/Running: Physical MEGAHIT \(0\/2\)/);
console.log("RESULTS_FIRST_OVERVIEW_JS_OK");
'''
        process=subprocess.run(["node","-e",script],cwd=ROOT,
                               capture_output=True,text=True,timeout=20)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertIn("RESULTS_FIRST_OVERVIEW_JS_OK",process.stdout)

    def test_podman_running_tools_are_separate_from_queued(self):
        images={"iva":"1"*64,"ivanka":"2"*64,"megahit":"3"*64}
        pod=type("Run",(),{"stdout":
            "ivanka-bench-iva-iva-a\t"+"1"*12+"\n"+
            "ivanka-bench-synth-xyz\t"+"3"*12+"\n"})()
        with patch.object(activity.subprocess,"run",return_value=pod):
            observed=activity.running(images)
        self.assertEqual(observed,{"real":["iva"],"synthetic":["megahit"]})

    def test_publisher_refuses_unverifiable_worker_claims(self):
        report={"runs":[{"tools":["iva","ivanka","megahit"]}]}
        data={"schema":activity.SCHEMA,"status":"observed",
              "order":["real","synthetic"],
              "running":{"real":["ivanka"],"synthetic":[]},
              "deferred":["ivanka"]}
        with self.assertRaisesRegex(ValueError,"deferred"):
            activity.validate(data,report)
        data["running"]["real"]=[]
        data["status"]="unavailable"
        self.assertIsNone(activity.validate(data,report))
        data["running"]["real"]=["iva"]
        with self.assertRaisesRegex(ValueError,"cannot claim running"):
            activity.validate(data,report)


if __name__=="__main__":
    unittest.main()

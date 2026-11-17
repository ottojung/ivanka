"""A bounded fair queue must preserve checkpoints and fill idle MiCall slots."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from expanded.balanced_dispatch import BalancedQueue,drive
from expanded import comparators_balanced_real as real
from expanded import comparators_balanced_synthetic as syn


TOOLS=("iva","haploflow","megahit","abyss","spades","velvet")
IMAGES={name:f"{i+1:064x}" for i,name in enumerate(TOOLS)}
CASES=list(range(198))


class FairDispatcherTests(unittest.TestCase):
    def test_previously_completed_iva_does_not_monopolize_new_work(self):
        queue=BalancedQueue(
            TOOLS,CASES,
            {tool:set(range(167)) if tool=="iva" else set()
             for tool in TOOLS},lambda case:case)
        assigned=[queue.take() for _ in range(10)]
        self.assertTrue(all(job[0]!="iva" for job in assigned))
        self.assertEqual(
            {tool:sum(job[0]==tool for job in assigned) for tool in TOOLS},
            {"iva":0,"haploflow":2,"megahit":2,"abyss":2,
             "spades":2,"velvet":2})
        self.assertEqual(queue.report()["iva"],(167,0,31))

    def test_dynamic_refill_no_duplicate_or_reexecution(self):
        cases=list(range(25))
        reused={"iva":set(range(8)), "haploflow":set(range(5)),
                "megahit":set(range(12))}
        tools=tuple(reused)
        q=BalancedQueue(tools,cases,reused,lambda x:x)
        calls=[]
        lock=threading.Lock()
        def perform(name,row):
            with lock:
                calls.append((name,row))
            return (name,row)
        def saved(name,key,result):
            self.assertEqual(result,(name,key))
        result=drive(q,4,perform,saved)
        self.assertEqual(result,{t:(25,0,0) for t in tools})
        self.assertEqual(len(calls),3*25-sum(map(len,reused.values())))
        self.assertEqual(len(calls),len(set(calls)))
        self.assertFalse(any(row in reused[name] for name,row in calls))
        self.assertEqual(set(calls),
                         {(t,x) for t in tools for x in cases
                          if x not in reused[t]})

    def test_early_completion_is_uneven_but_slots_stay_balanced(self):
        q=BalancedQueue(TOOLS,CASES,{t:set() for t in TOOLS},lambda x:x)
        start=[q.take() for _ in range(10)]
        first={t:sum(item[0]==t for item in start) for t in TOOLS}
        self.assertEqual(sorted(first.values()),[1,1,2,2,2,2])
        slow=start[0]
        q.complete(*slow[:2])
        next_one=q.take()
        self.assertIsNotNone(next_one)
        self.assertLessEqual(q.report()[next_one[0]][0],1)

    def test_torn_journal_cleanup_only_removes_temp_files(self):
        from expanded.balanced_dispatch import clear_stale_recovery
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)
            result=home/"results.recovered.partial"
            result.write_text("interrupted write")
            clear_stale_recovery(result)
            self.assertFalse(result.exists())
            original=home/"immutable-evidence.json"
            original.write_text("protected")
            result.symlink_to(original)
            with self.assertRaisesRegex(ValueError,"unsafe symlink"):
                clear_stale_recovery(result)
            self.assertEqual(original.read_text(),"protected")

    def test_invalid_work_and_out_of_cohort_replay_fail(self):
        with self.assertRaisesRegex(ValueError,"duplicate"):
            BalancedQueue(TOOLS,[1,1],{t:set() for t in TOOLS},lambda x:x)
        with self.assertRaisesRegex(ValueError,"not in the cohort"):
            BalancedQueue(TOOLS,[1],{"iva":{2},**{
                t:set() for t in TOOLS if t!="iva"}},lambda x:x)
        q=BalancedQueue(("iva",),[1],{"iva":set()},lambda x:x)
        with self.assertRaisesRegex(ValueError,"concurrency"):
            drive(q,11,lambda t,r:None,lambda t,k,r:None)

    def test_immutable_scheduler_receipts_detect_drift(self):
        with tempfile.TemporaryDirectory() as dirname:
            root=Path(dirname)
            (root/"run_manifest.json").write_text('{"legacy":true}')
            real.receipt(root)
            syn_path=root/"scheduler_receipt.json"
            self.assertIn("physical_scheduler_sha256",
                          json.loads(syn_path.read_text()))
            real.receipt(root)
            (root/"run_manifest.json").write_text('{"legacy":false}')
            with self.assertRaisesRegex(ValueError,"source changed"):
                real.receipt(root)


class SyntheticBalancedRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.sample=[(f"clonal-s{i:03d}",self.root/"inputs"/f"clonal-s{i:03d}",
                      {"family":"clonal","sha256":{
                          "reads/R1.fastq.gz":"a"*64,
                          "reads/R2.fastq.gz":"b"*64}})
                     for i in range(400)]
        (self.root/"results").mkdir()
        (self.root/"results"/"run_manifest.json").write_text('{"frozen":true}')
        self.calls=[]
        self.lock=threading.Lock()

    def fake_arm(self,case,destination,name,image,timeout):
        with self.lock:
            self.calls.append((name,destination.parent.name))
        destination.mkdir(parents=True,exist_ok=False)
        data=b"sequence\nACGT\n"
        (destination/"conseq.csv").write_bytes(data)
        record={"status":"success","score":4.,
                "exit_code":0,"seconds":1.,
                "score_origin":"micall_final_max_reference_panel_v1",
                "timing_origin":"micall_in_container_monotonic_v1",
                "sha256":image,"argv":["podman",image,"--all_projects"],
                "final_dominant":{"source_output":"conseq.csv",
                    "conseq_csv_sha256":hashlib.sha256(data).hexdigest()}}
        (destination/"execution.json").write_text(json.dumps(record))
        return record

    def test_complete_recovery_preserves_old_arms(self):
        proof={"valid":True}
        out=self.root/"results"
        sample=self.sample[0][0]
        self.fake_arm(None,out/sample/"iva","iva",IMAGES["iva"],1800)
        self.calls.clear()
        with (patch.object(syn,"checked_images"),
              patch.object(syn,"attestation",return_value=proof),
              patch.object(syn,"cohort_rows",return_value=self.sample),
              patch.object(syn,"source_manifest",
                           return_value={"frozen":True}),
              patch.object(syn,"attempt",side_effect=self.fake_arm)):
            first=syn.run(self.root/"inputs",out,
                          {**IMAGES,"ivanka":"7"*64},
                          None,syn.BASE,None,6)
            before=set(self.calls)
            self.assertNotIn(("iva",sample),before)
            self.assertEqual(len(self.calls),2399)
            self.calls.clear()
            second=syn.run(self.root/"inputs",out,
                           {**IMAGES,"ivanka":"7"*64},
                           None,syn.BASE,None,6)
        self.assertEqual(first,second)
        self.assertEqual(self.calls,[])
        self.assertEqual(
            len(list(out.glob("*/matrix.json"))),400)
        self.assertEqual(
            len((out/"results.jsonl").read_text().splitlines()),400)
        self.assertEqual(first["sample_count"],400)
        self.assertTrue(first["ivanka_deferred"])


if __name__=="__main__":
    unittest.main()

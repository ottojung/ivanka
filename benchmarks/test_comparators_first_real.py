"""Frozen physical comparator arms must not execute or invent Ivanka results."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from expanded import comparators_first_real as phase

IMAGES={name:f"{i+1:064x}" for i,name in enumerate(phase.TOOLS)}
CASE={"sample":"sample1","project":"NFLHIVDNA",
      "input_sha256":"0"*64,"micall_project_code":"NFLHIVDNA"}
PANEL=[("HXB2","ACGT")]


class PhysicalComparatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.pmm=SimpleNamespace(
            RESULTS=self.root/"artifacts",
            final_max_sequences=lambda folder:["ACGT"],
            best_panel_alignment=lambda seq,panel:{"score":4.},
            run_arm=self.arm,
        )
        self.calls=[]

    def arm(self,row,arm,image,reference,timeout,invocation,all_projects):
        self.calls.append((arm,image,timeout,all_projects))
        return {"image_id":image,"exit_code":0,"seconds":5.,
                "artifact_dir":str(self.root/"artifacts"/invocation/
                                   row["sample"]/arm)}

    def test_all_six_arms_never_use_ivanka(self):
        with patch.object(phase,"authentic_arm"):
            for name in phase.TOOLS:
                result=phase.execute(CASE,name,IMAGES,"ACGT",
                                     PANEL,self.pmm,self.root)
                self.assertFalse(result["failed"])
                self.assertEqual(result["measurement"]["score"],4.)
                self.assertEqual(result["measurement"]["seconds"],5.)
            self.assertEqual(len(self.calls),6)
            self.assertEqual([name for name in phase.TOOLS],
                             ["iva","haploflow","megahit","abyss","spades","velvet"])
            self.assertEqual([call[0] for call in self.calls],
                             ["iva"]+["ivanka"]*5)
            self.assertTrue(all(call[2]==1800 and call[3]
                                for call in self.calls))

    def test_completed_case_recovered_without_new_arm(self):
        with patch.object(phase,"authentic_arm"):
            phase.execute(CASE,"iva",IMAGES,"ACGT",PANEL,
                          self.pmm,self.root)
            folder=self.root/"iva"
            before=phase.replay(folder,[CASE],"iva",IMAGES["iva"],
                                PANEL,self.pmm)
            again=phase.replay(folder,[CASE],"iva",IMAGES["iva"],
                               PANEL,self.pmm)
            self.assertEqual(before,again)
            self.assertEqual(len(self.calls),1)
            self.assertEqual(len((folder/"results.jsonl").read_text().splitlines()),1)

    def test_score_tampering_rejected(self):
        with patch.object(phase,"authentic_arm"):
            phase.execute(CASE,"spades",IMAGES,"ACGT",PANEL,
                          self.pmm,self.root)
            target=phase.row_path(self.root/"spades",CASE["sample"])
            record=json.loads(target.read_text())
            record["measurement"]["score"]=999.
            target.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,"panel scoring changed"):
                phase.replay(self.root/"spades",[CASE],"spades",
                             IMAGES["spades"],PANEL,self.pmm)

    def test_no_ivanka_image_in_frozen_real_manifest(self):
        data=self.root/"dataset"
        data.mkdir()
        (data/"manifest.tsv").write_bytes(b"frozen")
        att=self.root/"proof.json"
        att.write_text("{}")
        with (patch.object(phase,"digest",side_effect=lambda p:
                           phase.MANIFEST if Path(p).name=="manifest.tsv"
                           else "a"*64)):
            manifest=phase.manifest(data,IMAGES,att,phase.PANEL)
        self.assertNotIn("ivanka",manifest["images"])
        self.assertTrue(manifest["ivanka_deferred"])


if __name__=="__main__":
    unittest.main()

"""A full resumed physical test must not replay any original completed arm."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from expanded import comparators_balanced_real as balanced
from expanded import comparators_first_real as legacy


TOOLS=legacy.TOOLS
IMAGES={name:f"{i+1:064x}" for i,name in enumerate(TOOLS)}


class PhysicalBalancedRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.out=self.root/"results"
        self.out.mkdir()
        self.data=self.root/"data"
        self.data.mkdir()
        (self.data/"hxb2.fasta").write_text(">HXB2\nACGT\n")
        (self.out/"run_manifest.json").write_text('{"frozen":true}')
        self.cases=[{"sample":f"physical_{i:03d}","project":"NFLHIVDNA",
                     "input_sha256":f"{i+1:064x}"} for i in range(198)]
        self.calls=[]
        self.mutex=threading.Lock()

    def checkpoint(self,row,tool):
        folder=self.out/tool/"checkpoints"
        folder.mkdir(exist_ok=True,parents=True)
        key=hashlib.sha256(row["sample"].encode()).hexdigest()
        return folder/(key+".json")

    def create(self,row,tool):
        record={"sample":row["sample"],"tool":tool,
                "status":"finished","failed":False,
                "image_id":IMAGES[tool],"measurement":{
                    "score":1.,"seconds":2.}}
        self.checkpoint(row,tool).write_text(json.dumps(record))
        return record

    def fake_execute(self,row,tool,images,hxb2,panel,pmm,out):
        with self.mutex:
            self.calls.append((tool,row["sample"]))
        return self.create(row,tool)

    def fake_replay(self,folder,cases,tool,image,panel,pmm):
        recovered={}
        for row in cases:
            path=self.checkpoint(row,tool)
            if path.exists():
                recovered[row["sample"]]=json.loads(path.read_text())
        journal=folder/"results.jsonl"
        journal.parent.mkdir(parents=True,exist_ok=True)
        journal.write_text("".join(json.dumps(entry,sort_keys=True)+"\n"
                         for entry in recovered.values()))
        return recovered

    def test_rebalance_resume_167_iva_without_rerun(self):
        for row in self.cases[:167]:
            self.create(row,"iva")
        import podman_full_micall as pmm
        import reference_panel
        patchers=(
            patch.object(balanced,"checked_images"),
            patch.object(balanced,"attest"),
            patch.object(balanced,"rows",return_value=self.cases),
            patch.object(balanced,"manifest",return_value={"frozen":True}),
            patch.object(balanced,"execute",side_effect=self.fake_execute),
            patch.object(balanced,"verify"),
            patch.object(balanced,"replay",side_effect=self.fake_replay),
            patch.object(pmm,"load_micall_projects",
                         return_value=({},None)),
            patch.object(reference_panel,"build_reference_panel",
                         return_value=[]),
            patch.object(reference_panel,"panel_sha256",
                         return_value=legacy.PANEL),
        )
        from contextlib import ExitStack
        with ExitStack() as stack:
            for entry in patchers:
                stack.enter_context(entry)
            with redirect_stdout(io.StringIO()):
                first=balanced.run(self.data,self.out,IMAGES,
                                   None,balanced.BASE,None,10)
            calls=set(self.calls)
            self.assertEqual(len(calls),6*198-167)
            self.assertFalse(any(
                t=="iva" and name in {row["sample"] for row
                in self.cases[:167]} for t,name in calls))
            self.assertEqual(len(calls),len(self.calls))
            for tool in TOOLS:
                self.assertEqual(len(list((
                    self.out/tool/"checkpoints").glob("*.json"))),198)
            self.calls.clear()
            with redirect_stdout(io.StringIO()):
                second=balanced.run(self.data,self.out,IMAGES,
                                    None,balanced.BASE,None,10)
        self.assertEqual(first,second)
        self.assertEqual(self.calls,[])
        self.assertEqual(first["samples"],198)
        self.assertTrue(first["ivanka_deferred"])
        self.assertNotIn("ivanka",first["tools"])


if __name__=="__main__":
    unittest.main()

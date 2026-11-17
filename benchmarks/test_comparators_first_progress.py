"""Published comparator progress must be partial, monotone and anonymous."""
import json
from pathlib import Path
import tempfile
import unittest

from expanded import comparators_first_progress as progress
from expanded.comparators_first_synthetic import TOOLS


class ComparatorPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.synthetic=root/"synthetic"
        self.real=root/"real"
        self.output=root/"progress.json"
        self.synthetic.mkdir()
        self.real.mkdir()

    def test_initial_zero_is_six_not_seven(self):
        result=progress.generate(self.synthetic,self.real)
        self.assertEqual(set(result["tools"]),set(TOOLS))
        self.assertEqual(result["ivanka"],"deliberately_deferred")
        for entry in result["tools"].values():
            self.assertEqual(entry["synthetic"]["expected"],400)
            self.assertEqual(entry["real"]["expected"],198)
        self.assertNotIn("Ivanka",json.dumps(result))

    def test_real_progress_omits_physical_sample_id(self):
        manifest={"schema":"ivanka.expanded.comparators_first_real.v1"}
        (self.real/"run_manifest.json").write_text(json.dumps(manifest))
        folder=self.real/"iva"
        folder.mkdir()
        rows=[
            {"sample":"PRIVATE_SAMPLE_ID_01","status":"finished",
             "failed":False,"measurement":{"score":260.,"seconds":15.}},
            {"sample":"PRIVATE_SAMPLE_ID_02","status":"finished",
             "failed":True,"measurement":None},
        ]
        (folder/"results.jsonl").write_text(
            "".join(json.dumps(row)+"\n" for row in rows))
        self.assertTrue(progress.publish(self.synthetic,self.real,self.output))
        report=json.loads(self.output.read_text())
        counts=report["tools"]["iva"]["real"]
        self.assertEqual((counts["completed"],counts["failed"]),(2,1))
        self.assertEqual(counts["mean_alignment"],260.)
        self.assertNotIn("PRIVATE_SAMPLE",self.output.read_text())
        self.assertFalse(progress.publish(self.synthetic,self.real,self.output))
        (folder/"results.jsonl").write_text(json.dumps(rows[0])+"\n")
        with self.assertRaisesRegex(ValueError,"regressed"):
            progress.publish(self.synthetic,self.real,self.output)


if __name__=="__main__":
    unittest.main()

"""Offline requalification must reject inconsistent source/provenance."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from replay_milestone198 import read_completed, restore


class ReplayTests(unittest.TestCase):
    def test_exactly_one_complete_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.jsonl"
            rows = [{"sample": f"S{i}", "invocation": "run", "status": "finished"}
                    for i in range(198)]
            path.write_text("\n".join(map(json.dumps, rows)))
            self.assertEqual(len(read_completed(path)), 198)
            rows[0]["invocation"] = "another"
            path.write_text("\n".join(map(json.dumps, rows)))
            with self.assertRaises(ValueError):
                read_completed(path)

    def test_missing_or_foreign_ivanka_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "sample"
            folder.mkdir()
            data = {"sample": "S", "status": "finished",
                    "ivanka": {"exit_code": 0, "image_id": "wrong",
                               "artifact_dir": str(folder),
                               "metrics": {"outputs": {"conseq.csv": {"sha256": "x"}}}}}
            with self.assertRaises(ValueError):
                restore({"sample": "S"}, data, Path(tmp), "iva", "ivanka", "hxb2", ())
            data["ivanka"]["image_id"] = "ivanka"
            with self.assertRaises(ValueError):
                restore({"sample": "S"}, data, Path(tmp), "iva", "ivanka", "hxb2", ())

    def test_mismatched_input_provenance_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "sample"
            folder.mkdir()
            (folder / "conseq.csv").write_text("fixture")
            data = {"sample": "S", "status": "finished", "provenance": {},
                    "ivanka": {"exit_code": 0, "image_id": "ivanka",
                               "artifact_dir": str(folder),
                               "metrics": {"outputs": {"conseq.csv": {"sha256": "ok"}}}}}
            with (patch("replay_milestone198.sha", return_value="ok"),
                  patch("replay_milestone198.baseline_provenance",
                        return_value={"expected": "proof"})):
                with self.assertRaises(ValueError):
                    restore({"sample": "S"}, data, Path(tmp), "iva", "ivanka", "hxb2", ())


if __name__ == "__main__":
    unittest.main()

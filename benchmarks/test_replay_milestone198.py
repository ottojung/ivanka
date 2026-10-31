"""Offline requalification must reject inconsistent source/provenance."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from replay_milestone198 import collect_completed, read_completed, restore


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

    def test_disjoint_interrupted_invocations_retain_source_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            roots = [Path(tmp) / "a", Path(tmp) / "b"]
            for root in roots:
                root.mkdir()
            first = [{"sample": f"S{i}", "invocation": "run-a", "status": "finished"}
                     for i in range(26)]
            second = [{"sample": f"S{i}", "invocation": "run-b", "status": "finished"}
                      for i in range(26, 198)]
            for root, rows in zip(roots, (first, second)):
                (root / "results.jsonl").write_text(
                    "\n".join(json.dumps(row) for row in rows))
            with self.assertRaises(ValueError):
                read_completed(roots[0] / "results.jsonl")
            combined, sources = collect_completed(roots)
            self.assertEqual(len(combined), 198)
            self.assertEqual([s["completed_samples"] for s in sources], [26, 172])
            self.assertEqual(combined["S0"][0]["invocation"], "run-a")
            self.assertEqual(combined["S197"][0]["invocation"], "run-b")
            self.assertEqual(combined["S197"][1], roots[1].resolve())
            self.assertEqual(len(sources[0]["results_sha256"]), 64)

            second[0]["sample"] = "S0"
            (roots[1] / "results.jsonl").write_text(
                "\n".join(json.dumps(row) for row in second))
            with self.assertRaisesRegex(ValueError, "Overlapping"):
                collect_completed(roots)
            second[0]["sample"] = "S26"
            second[0]["invocation"] = "run-a"
            (roots[1] / "results.jsonl").write_text(
                "\n".join(json.dumps(row) for row in second))
            with self.assertRaises(ValueError):
                collect_completed(roots)

    def test_empty_and_mixed_invocation_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.jsonl"
            path.write_text("")
            with self.assertRaises(ValueError):
                read_completed(path, require_full=False)
            path.write_text("\n".join(json.dumps(row) for row in (
                {"sample": "S1", "invocation": "a", "status": "finished"},
                {"sample": "S2", "invocation": "b", "status": "finished"})))
            with self.assertRaises(ValueError):
                read_completed(path, require_full=False)

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

    def test_recovered_real_control_allows_scoring_without_assembly(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "sample"
            folder.mkdir()
            (folder / "conseq.csv").write_text("fixture")
            data = {"sample": "S", "status": "finished", "failed": True,
                    "baseline_error": "missing when executed",
                    "evaluation_error": "missing baseline",
                    "provenance": {"auth": True}, "total_seconds": 100.,
                    "ivanka": {"exit_code": 0, "image_id": "ivanka",
                               "artifact_dir": str(folder),
                               "metrics": {"outputs": {"conseq.csv":
                                           {"sha256": "proof"}}}}}
            with (patch("replay_milestone198.sha", return_value="proof"),
                  patch("replay_milestone198.baseline_provenance",
                        return_value={"auth": True}),
                  patch("replay_milestone198.load_iva_baseline",
                        return_value={"artifact_dir": str(folder)}),
                  patch("replay_milestone198.panel_acceptance",
                        return_value={"pass": True})):
                restored = restore({"sample": "S"}, data, Path(tmp),
                                   "iva", "ivanka", "hxb2", ())
            self.assertFalse(restored["failed"])
            self.assertTrue(restored["iva_baseline_reused"])
            self.assertNotIn("evaluation_error", restored)
            self.assertEqual(restored["total_seconds"], 100.)
            self.assertGreaterEqual(restored["replay_validation_seconds"], 0)
            self.assertTrue(restored["source_diagnostic_failed"])

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

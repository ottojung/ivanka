"""Compact per-sample MiCall outputs without changing scored evidence."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import hashlib
import json

from expanded import micall_synthetic as runner
from retained_artifacts import MAX_FILE_BYTES


class CompactAttemptTests(TestCase):
    def _run(self, successful):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            case = root / "case"
            case.mkdir()
            arm = root / "arm"
            original = b"seed,consensus-percent-cutoff,sequence\nX,MAX,ACGT\n"
            digest = hashlib.sha256(original).hexdigest()

            def fake_run(*args, **kwargs):
                scratch = arm / "scratch"
                scratch.mkdir()
                (scratch / "conseq.csv").write_bytes(original)
                (scratch / "temp.sam").write_bytes(b"A" * (MAX_FILE_BYTES + 1))
                (arm / "timing.json").write_text(json.dumps({
                    "timing_origin": runner.TIMING_ORIGIN, "exit_code": 0,
                    "seconds": 0.01,
                }))
                return SimpleNamespace(
                    returncode=0 if successful else 1, stage="finished")

            evidence = {"score_origin": runner.SCORE_ORIGIN,
                        "score": 1.0, "dominant_exact": True,
                        "source": {
                            "source_output": "scratch/conseq.csv",
                            "conseq_csv_sha256": digest,
                        }}
            with patch.object(runner, "run_detached", side_effect=fake_run), (
                    patch.object(runner, "evaluate_final_alignment",
                                 return_value=evidence)), (
                    patch.object(runner, "public_diagnostics",
                                 return_value={"status": "recorded"})):
                result = runner.attempt((case, {"hidden_truth_file": "truth"}),
                                        arm, "ivanka", "image", 100)
            self.assertEqual(result["status"],
                             "success" if successful else "failed")
            self.assertFalse((arm / "scratch").exists())
            self.assertFalse((arm / "temp.sam").exists())
            self.assertTrue((arm / "execution.json").is_file())
            self.assertTrue((arm / "stderr.log").is_file())
            self.assertEqual(result["diagnostics"]["status"], "recorded")
            if successful:
                self.assertEqual(
                    result["final_dominant"]["source_output"], "conseq.csv")
                self.assertEqual((arm / "conseq.csv").read_bytes(), original)
            else:
                self.assertIn("MiCall exited", result["error"])

    def test_success_keeps_scored_consensus(self):
        self._run(True)

    def test_failure_keeps_small_diagnostics_without_bulky_scratch(self):
        self._run(False)

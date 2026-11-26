"""Missing, mismatched and ambiguous historical evidence is not measured."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from px_native_runtime_diagnostic import duration, evaluate, measurement


class NativeTimingTest(unittest.TestCase):
    def test_one_native_duration(self):
        self.assertEqual(duration("Assembled 3 contigs in 0:01:02.25 (62s)"), (3, 62.25))
        for text in ("", "Assembled 2 contigs in 0:00:60",
                     "Assembled 2 contigs in 0:00:01\nAssembled 3 contigs in 0:00:02"):
            with self.assertRaises(ValueError):
                duration(text)

    def test_attested_success_and_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "run.log"
            p.write_text("Assembled 3 contigs in 0:00:05.5")
            arm = {"tool_id": "ray", "seconds": 20,
                   "runner_receipt_sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            launcher = {"tool": "ray", "status": "finished", "exit_code": 0,
                        "bound_cid": "a" * 64}
            self.assertEqual(measurement(arm, launcher, p)["unattributed_seconds"], 14.5)
            for field, bad in (("exit_code", 1), ("tool", "minia"), ("status", "failed"),
                               ("bound_cid", "a" * 12)):
                with self.assertRaisesRegex(ValueError, "attested"):
                    measurement(arm, dict(launcher, **{field: bad}), p)
            with self.assertRaisesRegex(ValueError, "exceeds"):
                measurement(dict(arm, seconds=5), launcher, p)
            p.write_text("changed")
            with self.assertRaisesRegex(ValueError, "digest"):
                measurement(arm, launcher, p)


    def test_index_hash_and_ambiguous_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipts = root / "receipts"
            receipts.mkdir()
            log = root / "run-ray-1.log"
            log.write_text("Assembled 1 contigs in 0:00:02")
            log_hash = hashlib.sha256(log.read_bytes()).hexdigest()
            report = {"tool": "ray", "status": "finished", "exit_code": 0,
                      "bound_cid": "a" * 64, "log_sha256": log_hash}
            (root / "run-ray-1.json").write_text(json.dumps(report))
            ident = "ray-physical-PX-R001"
            arm = {"schema": "ivanka.px.case.receipt.v1", "terminal": True,
                   "qualifying": False, "tool_id": "ray", "cohort": "physical",
                   "alias": "PX-R001", "outcome": "success", "seconds": 20,
                   "runner_receipt_sha256": log_hash}
            p = receipts / (ident + ".json")
            p.write_text(json.dumps(arm))
            (receipts / "index.json").write_text(json.dumps(
                {"entries": {ident: hashlib.sha256(p.read_bytes()).hexdigest()}}))
            self.assertEqual(evaluate(root)["matched_successes"], 1)
            (root / "run-ray-2.json").write_text(json.dumps(report))
            x = evaluate(root)
            self.assertEqual(x["matched_successes"], 0)
            self.assertEqual(x["groups"][0]["unavailable"],
                             {"missing_or_ambiguous_launcher_report": 1})
            p.write_text("{}")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                evaluate(root)

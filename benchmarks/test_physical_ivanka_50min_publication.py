"""Publish source-proven 50-minute physical Ivanka runs without 30m rejection."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
from unittest import TestCase

from benchmarks.assembler_bench.current_inputs import (
    accept, real_arm, sample)


class PhysicalIvankaPublicationTests(TestCase):
    def test_extended_ivanka_run_accepts_2400_seconds_and_original_30m_does_not(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            name = "case"
            image = "a" * 64
            source = root / "original"
            pair = [{"sha256": "a" * 64}, {"sha256": "b" * 64}]
            hashpair = hashlib.sha256(("a" * 64 + "b" * 64).encode()).hexdigest()
            output = source / "artifacts" / "try" / name / "ivanka"
            output.mkdir(parents=True)
            data = b"consensus-percent-cutoff,sequence\nMAX,ACGT\n"
            (output / "conseq.csv").write_bytes(data)
            original = {
                "sample": name, "tool": "ivanka", "image_id": image,
                "input_sha256": hashpair,
                "reference_panel_sha256":
                    "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8",
                "status": "finished", "failed": False,
                "arm": {"image_id": image, "exit_code": 0,
                        "artifact_dir": str(output), "seconds": 2400.0,
                        "metrics": {"outputs": {"conseq.csv": {
                            "sha256": hashlib.sha256(data).hexdigest()}}}},
                "measurement": {"seconds": 2400.0, "score": 95.0},
                "resource_timeout_seconds": 3000,
            }
            checkpoint = (source / "ivanka" / "checkpoints" /
                          (hashlib.sha256(name.encode()).hexdigest() + ".json"))
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text(json.dumps(original))
            evidence = real_arm(source, "ivanka", name, image, pair)
            self.assertEqual(evidence["time_budget_seconds"], 3000)
            row = sample("R001", ("ivanka",))
            accept(row, "ivanka", evidence, {})
            self.assertEqual(row["seconds"]["ivanka"], 2400.0)
            original["resource_timeout_seconds"] = 1800
            checkpoint.write_text(json.dumps(original))
            with self.assertRaisesRegex(ValueError, "50m"):
                real_arm(source, "ivanka", name, image, pair)

    def test_original_six_keep_1800_second_limit(self):
        from benchmarks.assembler_bench.current_inputs import accept
        row = sample("R001", ("iva",))
        with self.assertRaises(ValueError):
            accept(row, "iva", {"status":"success",
                                "score": 95.0, "seconds": 2400.0}, {})

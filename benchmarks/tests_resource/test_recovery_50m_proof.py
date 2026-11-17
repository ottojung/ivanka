"""Original 30m and extended 50m proof rules remain independently enforced."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
from unittest import TestCase
from unittest.mock import Mock

from benchmarks.expanded.comparators_first_real import PANEL
from benchmarks.expanded.comparators_first_real import verify as original_verify
from benchmarks.real_recovery.proof import verify as verify_retry


class ExtendedProofTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / "artifact" / "case" / "ivanka"
        self.folder.mkdir(parents=True)
        self.outputs = {}
        for n in range(11):
            name = f"output-{n}.csv"
            path = self.folder / name
            path.write_text(f"row,{n}\n")
            self.outputs[name] = {"exists": True,
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        (self.folder / "podman.stderr.log").write_text(
            "MiCall started\nmicall.process_run(): Done.\n")
        self.row = {"sample": "case", "input_sha256": "inputs"}
        self.arm = {
            "image_id": "image", "exit_code": 0,
            "timing_origin": "micall_in_container_monotonic_v1",
            "seconds": 2400.0, "container_wall_seconds": 2400.5,
            "artifact_dir": str(self.folder),
            "metrics": {"outputs": self.outputs},
        }
        self.record = {
            "sample": "case", "input_sha256": "inputs", "tool": "abyss",
            "image_id": "image", "reference_panel_sha256": PANEL,
            "status": "finished", "failed": False,
            "arm": self.arm, "measurement": {"seconds": 2400.0, "score": 42.0}
        }
        self.pmm = Mock(RESULTS=self.root,
                        final_max_sequences=Mock(return_value=["ACGT"]),
                        best_panel_alignment=Mock(return_value={"score": 42.0}))
        self.timer()

    def timer(self, seconds=2400.0):
        (self.folder / "micall_internal_timing.json").write_text(
            json.dumps({"exit_code": 0, "seconds": seconds,
                        "timing_origin": "micall_in_container_monotonic_v1"}))

    def test_original_30m_rejects_new_extended_valid_success(self):
        with self.assertRaisesRegex(ValueError, "incompatible original"):
            original_verify(self.record, self.row, "abyss", "image", [], self.pmm)
        self.assertIs(self.record, verify_retry(
            self.record, self.row, "abyss", "image", [], self.pmm))

    def test_extended_verifier_rejects_modified_timing_score_and_output(self):
        self.timer(2200.0)
        with self.assertRaisesRegex(ValueError, "timer evidence differs"):
            verify_retry(self.record, self.row, "abyss", "image", [], self.pmm)
        self.timer()
        self.record["measurement"]["score"] = 41.0
        with self.assertRaisesRegex(ValueError, "alignment score differs"):
            verify_retry(self.record, self.row, "abyss", "image", [], self.pmm)
        self.record["measurement"]["score"] = 42.0
        (self.folder / "output-0.csv").write_text("tampered\n")
        with self.assertRaisesRegex(ValueError, "output hash mismatch"):
            verify_retry(self.record, self.row, "abyss", "image", [], self.pmm)

    def test_extended_verifier_rejects_over_budget_and_wrong_root(self):
        self.arm["seconds"] = 3100.0
        self.arm["container_wall_seconds"] = 3100.5
        with self.assertRaisesRegex(ValueError, "budget"):
            verify_retry(self.record, self.row, "abyss", "image", [], self.pmm)
        self.arm["seconds"] = 2400.0
        self.arm["container_wall_seconds"] = 2400.5
        self.pmm.RESULTS = self.root / "wrong"
        with self.assertRaisesRegex(ValueError, "outside retry directory"):
            verify_retry(self.record, self.row, "abyss", "image", [], self.pmm)

    def test_failed_retry_uses_unmodified_original_failure_checker(self):
        self.record["failed"] = True
        self.record["measurement"] = None
        self.arm["exit_code"] = 255
        self.assertIs(self.record, verify_retry(
            self.record, self.row, "abyss", "image", [], self.pmm))

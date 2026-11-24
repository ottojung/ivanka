"""Focused test: proven-dead P1 failures retire disposable scratch, keep evidence."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expanded import p1_full464_controller as controller


class FailureRetirementTests(unittest.TestCase):
    def test_failure_evidence_is_sealed_then_common_retire_runs_on_dead_container(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / "podman.log").write_text("MiCall failed\n")
            candidate = {"exit_code": 1, "error": "low-depth", "wall_seconds": 12,
                         "container_name": "ivanka-p1-test"}
            hashes = {"input.fastq.gz": "a" * 64}
            fake_evidence = folder / "terminal_evidence.json"
            fake_evidence.write_text("{}")
            with (
                mock.patch.object(controller, "seal_terminal_evidence",
                                  return_value=(fake_evidence, None)) as seal,
                mock.patch.object(controller, "container_dead",
                                  return_value=True) as dead,
                mock.patch.object(controller, "terminal_retire",
                                  return_value={"retired": True, "applied": True}) as retire,
            ):
                report = controller.terminal_retirement(
                    folder, candidate, False, hashes, {})
            self.assertTrue(report["retired"])
            self.assertTrue(seal.called)
            evidence = seal.call_args.args[1]
            self.assertIn("failure", evidence)
            self.assertEqual(evidence["failure"]["exit_code"], 1)
            probe = retire.call_args.kwargs["container_dead"]
            self.assertTrue(callable(probe))
            self.assertEqual(retire.call_args.kwargs["source_hashes"], hashes)
            self.assertEqual(retire.call_args.kwargs["evidence_path"], fake_evidence)

    def test_dead_probe_is_passed_through_as_a_callable(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / "podman.log").write_text("MiCall failed\n")
            fake_evidence = folder / "terminal_evidence.json"
            fake_evidence.write_text("{}")
            with (
                mock.patch.object(controller, "seal_terminal_evidence",
                                  return_value=(fake_evidence, None)),
                mock.patch.object(controller, "container_dead", return_value=False),
                mock.patch.object(controller, "terminal_retire",
                                  return_value={"applied": False}) as retire,
            ):
                controller.terminal_retirement(
                    folder, {"exit_code": 1, "container_name": "x"},
                    False, {"a": "b"}, {})
            probe = retire.call_args.kwargs["container_dead"]
            self.assertTrue(callable(probe))
            # terminal_retire, not this helper, evaluates the probe and fails
            # closed when it does not return True.


if __name__ == "__main__":
    unittest.main()

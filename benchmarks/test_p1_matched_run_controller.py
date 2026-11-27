"""Tests for the source-only matched-run controller."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import p1_matched_run_controller as controller
import p1_ultradeep_matched_runtime as plan
from fail_closed_guard import p1_harness

RECEIPT = (
    pathlib.Path(__file__).parent.parent
    / "docs/bench/diagnostics/p1-ultradeep-runtime-20261126.json"
)


def record(output_root: pathlib.Path, *, attestation: pathlib.Path | None = None) -> dict:
    return controller.build_controller_record(RECEIPT, output_root, attestation=attestation)


class ControllerTest(unittest.TestCase):
    def test_record_is_source_only_and_always_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "out"
            built = record(root)
            self.assertEqual(built["schema"], controller.CONTROLLER_SCHEMA)
            self.assertEqual(built["plan_schema"], plan.SCHEMA)
            self.assertEqual(built["execution"], "blocked")
            self.assertFalse(built["scientific_gates_changed"])
            self.assertFalse(built["formal_qualification"])
            self.assertFalse(built["dependencies"]["ready"])
            self.assertNotIn("execute", built)
            self.assertFalse(root.exists())

    def test_original_inputs_timer_and_images_are_retained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            built = record(pathlib.Path(tmp) / "out")
        self.assertEqual(built["inputs"]["reads"],
                         {c: plan.READ_SHA256[c] for c in plan.CASES})
        self.assertEqual(built["inputs"]["timer_sha256"], plan.TIMER_SHA256)
        self.assertEqual(built["timer_sha256"], plan.TIMER_SHA256)
        self.assertEqual(built["images"], {
            "frozen": plan.FROZEN_IMAGE, "candidate": plan.CANDIDATE_IMAGE})
        self.assertEqual(built["candidate_commit"], plan.CANDIDATE_COMMIT)
        self.assertEqual(built["source_pins"], plan.SOURCE_PINS)
        self.assertEqual(built["deployed_pins"], plan.DEPLOYED_PINS)

    def test_real_cli_template_and_reference_blind_guard_are_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            built = record(pathlib.Path(tmp) / "out")
        template = built["cli_template"]
        self.assertEqual(template["real_template"], controller.REAL_TEMPLATE)
        self.assertEqual(template["verified_arms"], 8)
        self.assertTrue(template["tail"])
        self.assertIn("--all_projects", template["tail"])
        self.assertEqual(len(built["schedule"]), 8)
        self.assertEqual(built["guard_integration"]["module"], controller.GUARD_MODULE)
        for key, value in p1_harness.P1_ATTESTATION.items():
            self.assertEqual(built["guard_integration"][key], value)
        self.assertFalse(built["guard_integration"]["kernel_enforcement"])

    def test_mutated_argv_is_refused_by_the_real_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            built = record(pathlib.Path(tmp) / "out")
        mutated = copy.deepcopy(built)
        mutated["schedule"][0]["argv"].append("--unexpected-flag")
        with self.assertRaises(controller.Refusal):
            controller.verify_cli_template(mutated)

    def test_truthful_attestation_still_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            path = folder / "attestation.json"
            body = {
                "schema": plan.ATTESTATION_SCHEMA,
                "PR535": {"state": "merged", "head": plan.SOURCE_PINS["PR535"]["head"],
                          "merge_commit": plan.SOURCE_PINS["PR535"]["merge_commit"]},
                "PR536": {"state": "merged", "head": plan.SOURCE_PINS["PR536"]["head"],
                          "merge_commit": plan.SOURCE_PINS["PR536"]["merge_commit"]},
                "deployed_sources": {"PR535": False, "PR536": True},
                "deployed_guard": {
                    "source_head": plan.DEPLOYED_PINS["guard_source_head"],
                    "root_head": plan.DEPLOYED_PINS["deployed_root_head"],
                    "tree_clean": True,
                    "guard_sha256": dict(plan.DEPLOYED_PINS["guard_sha256"]),
                    "px_service_head": plan.DEPLOYED_PINS["px_service_head"],
                    "watchdog_service_head": plan.DEPLOYED_PINS["watchdog_service_head"],
                    "watchdog_alive_fresh": True, "lease_clear": True,
                    "idle_boundary_attested": True,
                },
                "attested_by": "operator", "attested_at_utc": "2026-11-27T00:00:00Z",
            }
            path.write_text(json.dumps(body))
            built = record(folder / "out", attestation=path)
        self.assertFalse(built["dependencies"]["ready"])
        self.assertEqual(built["dependencies"]["blocked_by"], ["PR535"])
        self.assertEqual(built["execution"], "blocked")

    def test_emit_is_inert_unless_explicitly_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            root = base / "fresh"
            target = root / "controller.json"
            import sys
            saved = sys.argv
            try:
                sys.argv = ["p1_matched_run_controller", "--output-root", str(base / "out"),
                            "--emit-plan", str(target)]
                controller.main()
            finally:
                sys.argv = saved
            self.assertEqual(json.loads(target.read_text())["execution"], "blocked")
            self.assertFalse((base / "out").exists())


if __name__ == "__main__":
    unittest.main()

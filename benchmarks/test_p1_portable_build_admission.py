"""Deterministic source-only tests for the portable guarded-build preflight.

No podman, image, container, shared lock/watchdog, arm, benchmark or frozen
artifact is touched. All inputs are synthetic and confined to temp dirs.
"""
import json
import stat
import tempfile
import unittest
from pathlib import Path

from expanded import p1_bounded_pilot_runner as runner
from expanded import p1_portable_build_admission as admission
from fail_closed_guard import copy_overlay

SOURCE = "950fe331dfcd857011bfd63f9eeca92462708545"


def fixture(root):
    portable = root / "portable-bytes"
    portable.write_bytes(b"PORTABLE-950FE331-BYTES")
    native = root / "native-bytes"
    native.write_bytes(b"NATIVE-BYTES-UNCHANGED")
    row = {
        "source_commit": SOURCE,
        "role": "bounded-prospective-p1-950fe331",
        "portable_binary_sha256": runner.sha256(portable),
        "native_binary_sha256": runner.sha256(native),
        "portable_binary_path": str(portable),
        "native_binary_path": str(native),
    }
    other = dict(row, source_commit="1" * 64, role="pcr")
    material = root / "materialization.json"
    material.write_text(json.dumps({"status": "PORTABLE_BYTES_PRODUCED_NOT_IMAGE_BUILT"}))
    plan = {
        "schema": "ivanka.p1.portable-artifact-plan.v1",
        "candidates": [row, other],
        "materialization_receipt": {
            "path": str(material), "sha256": runner.sha256(material),
            "independent_elf_evidence_sha256": "f" * 64,
        },
    }
    return plan, row


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.plan, self.row = fixture(self.root)

    def test_candidate_row_is_exactly_one_planned_source(self):
        row = admission.candidate_row(self.plan)
        self.assertEqual(row["source_commit"], SOURCE)
        self.assertEqual(row["portable_binary_sha256"],
                         runner.sha256(Path(row["portable_binary_path"])))
        with self.assertRaises(ValueError):
            admission.candidate_row(self.plan, source_commit="2" * 64)

    def test_readiness_detects_disk_shortfall_without_touching_live_state(self):
        class Usage:
            def __init__(self, free):
                self.free = free

        short = admission.readiness(
            plan=self.plan, disk_usage_fn=lambda _p: Usage(29 * 1024 ** 3))
        self.assertFalse(short["disk"]["operator_ready"])
        self.assertEqual(short["disk"]["operator_floor_bytes"],
                         35 * 1024 ** 3)
        self.assertTrue(short["portable_binary"]["sha256"] ==
                        self.row["portable_binary_sha256"])
        self.assertIn("BLOCKED", short["launch"])
        ready = admission.readiness(
            plan=self.plan, disk_usage_fn=lambda _p: Usage(36 * 1024 ** 3))
        self.assertTrue(ready["disk"]["operator_ready"])
        self.assertEqual(ready["build_executed"], None)

    def test_stage_context_copies_only_portable_bytes(self):
        out = self.root / "namespace"
        context = admission.stage_context(out, self.row)
        self.assertEqual(sorted(p.name for p in context.iterdir()),
                         ["Containerfile", "ivanka"])
        self.assertEqual(runner.sha256(context / "ivanka"),
                         self.row["portable_binary_sha256"])
        self.assertNotEqual(runner.sha256(context / "ivanka"),
                            self.row["native_binary_sha256"])
        self.assertEqual(stat.S_IMODE((context / "ivanka").stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((context / "Containerfile").stat().st_mode), 0o400)
        self.assertEqual((context / "Containerfile").read_text(),
                         copy_overlay.CONTAINERFILE.format(
                             base="sha256:" + runner.PARENT_IMAGE))
        with self.assertRaises(ValueError):
            admission.stage_context(out, self.row)

    def test_plan_binds_portable_sha_role_and_helper_pin(self):
        conf = self.root / "storage.conf"
        conf.write_text("[storage]\n")
        code = self.root / "code"
        helper = code / "benchmarks/fail_closed_guard/copy_overlay_helper.py"
        helper.parent.mkdir(parents=True)
        helper.write_bytes(b"# pinned helper\n")
        context = admission.stage_context(self.root / "namespace2", self.row)
        plan = admission.plan_for_row(
            self.row, context=context, storage_conf=conf,
            base_layers=["sha256:" + "b" * 64], code_root=code)
        self.assertEqual(plan["schema"], copy_overlay.SCHEMA)
        self.assertEqual(plan["artifact_sha256"], self.row["portable_binary_sha256"])
        self.assertEqual(plan["pilot_role"], self.row["role"])
        self.assertEqual(plan["source_commit"], SOURCE)
        self.assertEqual(plan["destination"], "/usr/local/bin/ivanka")
        self.assertEqual(plan["code_sha256"], runner.sha256(helper))
        self.assertEqual(plan["storage_conf_sha256"], runner.sha256(conf))
        first = copy_overlay.plan_digest(plan)
        plan["artifact_sha256"] = self.row["native_binary_sha256"]
        self.assertNotEqual(copy_overlay.plan_digest(plan), first)

    def test_rendered_invocations_carry_receipt_flags_and_seven_cases(self):
        inv = admission.render_invocations(
            plan_path=self.root / "plan.json",
            receipt_path=self.root / "receipt.json",
            receipt_sha="d" * 64, out=self.root)
        self.assertIn("copy_overlay.run", inv["guarded_build"])
        self.assertIn("--portable-postbuild-receipt", inv["pilot_check"])
        self.assertIn("d" * 64, inv["pilot_check"])
        cases = inv["pilot_check"].split("--cases ")[1].strip().strip("'")
        self.assertEqual(len(cases.split(",")), 7)
        self.assertIn("physical-canary-R042", cases)
        self.assertIn("--operator-confirm", inv["postbuild_receipt"])

    def test_receipt_writer_is_fail_closed_and_binds_result(self):
        namespace = self.root / "receipt-ns"
        namespace.mkdir()
        result = namespace / "copy-overlay-result.json"
        result.write_text("{}")
        with self.assertRaises(ValueError):
            admission.write_receipt(
                namespace, plan=self.plan, result=result,
                image_digest="e" * 64, operator_confirm="", verify=False)
        made = admission.write_receipt(
            namespace, plan=self.plan, result=result,
            image_digest="sha256:" + "e" * 64,
            operator_confirm="owner-x", verify=False)
        doc = made["doc"]
        self.assertEqual(doc["schema"], runner.PORTABLE_POSTBUILD_SCHEMA)
        self.assertEqual(doc["source_commit"], SOURCE)
        self.assertEqual(doc["portable_binary_sha256"],
                         self.row["portable_binary_sha256"])
        self.assertEqual(doc["image_digest"], "e" * 64)
        self.assertEqual(doc["copy_overlay_result"]["sha256"], runner.sha256(result))
        self.assertEqual(made["sha256"], runner.sha256(made["path"]))
        with self.assertRaises(ValueError):
            admission.write_receipt(
                namespace, plan=self.plan, result=result,
                image_digest="e" * 64, operator_confirm="owner-x", verify=False)
        with self.assertRaises(ValueError):
            admission.write_receipt(
                namespace / "other", plan=self.plan, result=result,
                image_digest="e" * 64, operator_confirm="owner-x", verify=True)


if __name__ == "__main__":
    unittest.main()

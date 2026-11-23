"""Safety tests for the hosted PX build readiness audit (no OCI execution)."""
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from assembler_bench import frozen_contract
from assembler_bench.exploratory_policy import EXPERIMENTAL, checked
from assembler_bench.fork_image_attestation import FORK_FILES
from assembler_bench.micall_source_guard import fork_commit_url
from px_build_readiness import FORBIDDEN, REGISTRY, audit

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / "docs" / "bench" / "px-hosted-gha-workflow.yml.example"


def attestation(adapter, **overrides):
    data = {
        "schema": "ivanka.px.shared-source-attestation.v1",
        "source_commit": adapter,
        "baseline_commit": frozen_contract.COMMIT,
        "source_url": fork_commit_url(adapter),
        "baseline_url": fork_commit_url(frozen_contract.COMMIT),
        "frozen_tree": frozen_contract.TREE,
        "frozen_manifest_sha256": frozen_contract.MANIFEST,
        "independently_verified": True,
        "denovo_calls_environment_dispatcher": False,
        "shared_files": {name: "a" * 64 for name in FORK_FILES},
    }
    data.update(overrides)
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(data, handle)
    handle.close()
    return Path(handle.name)


def request(path=None, adapter="f" * 40, **overrides):
    data = {
        "tool": "skesa",
        "adapter_repo": "https://github.com/ottojung/MiCall",
        "adapter_commit": adapter,
        "base_commit": frozen_contract.COMMIT,
        "attestation_path": str(path or attestation(adapter)),
        "common_base_digest": "sha256:" + "b" * 64,
        "image_persistence": "ghcr-by-digest",
    }
    data.update(overrides)
    return data


class ReadinessTest(unittest.TestCase):
    def test_frozen_base_differs_from_px_adapters(self):
        reg = checked(REGISTRY)
        self.assertNotEqual(reg["adapter_baseline_commit"],
                            frozen_contract.COMMIT)
        self.assertEqual(reg["policy"]["frozen_seven_manifest_sha256"],
                         frozen_contract.MANIFEST)

    def test_valid_rebased_request(self):
        report = audit(request())
        self.assertEqual(report["status"], "source-audit-pass")
        self.assertTrue(report["prerequisites_met"])
        self.assertFalse(report["builds_permitted"])
        self.assertTrue(report["frozen_seven_intact"])
        self.assertEqual(report["base_commit"], frozen_contract.COMMIT)

    def test_old_eeca_adapter_is_blocked(self):
        reg = checked(REGISTRY)
        old = reg["adapter_branch_commits"]["skesa"]
        report = audit(request(path=attestation(old), adapter=old))
        self.assertFalse(report["prerequisites_met"])
        self.assertTrue(report["old_lineage_rejected"])
        self.assertTrue(any("rebase required" in b for b in report["blockers"]))

    def test_non_frozen_base_is_blocked(self):
        report = audit(request(base_commit="e" * 40))
        self.assertTrue(any("frozen MiCall commit" in b
                            for b in report["blockers"]))

    def test_denovo_dispatcher_call_is_blocked(self):
        path = attestation("f" * 40,
                           denovo_calls_environment_dispatcher=True)
        report = audit(request(path=path))
        self.assertTrue(any("denovo" in b for b in report["blockers"]))

    def test_missing_shared_file_hash_is_blocked(self):
        path = attestation("f" * 40, shared_files={"denovo.py": "a" * 64})
        report = audit(request(path=path))
        self.assertTrue(any("shared-source" in b for b in report["blockers"]))

    def test_missing_common_base_is_blocked(self):
        report = audit(request(common_base_digest=""))
        self.assertTrue(any("common-base" in b
                            for b in report["blockers"]))

    def test_reference_material_rejected(self):
        path = attestation("f" * 40, shared_files={
            **{name: "a" * 64 for name in FORK_FILES},
            "REFERENCE_FASTA": "hxb2.fa",
        })
        with self.assertRaises(ValueError):
            audit(request(path=path))

    def test_bad_attestation_schema_rejected(self):
        path = attestation("f" * 40, schema="unknown.v1")
        with self.assertRaises(ValueError):
            audit(request(path=path))

    def test_unknown_tool_rejected(self):
        with self.assertRaises(ValueError):
            audit(request(tool="ivanka"))


class WorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text()
        cls.doc = yaml.safe_load(cls.text)
        cls.triggers = cls.doc.get("on", cls.doc.get(True))

    def test_manual_dispatch_only(self):
        self.assertEqual(set(self.triggers), {"workflow_dispatch"})

    def test_no_build_or_publish_capability(self):
        lowered = self.text.lower()
        for token in ("podman", "docker/login", "podman push", "--mode build",
                      "pull-request", "packages: write"):
            self.assertNotIn(token, lowered)
        self.assertEqual(self.doc["permissions"], {"contents": "read"})

    def test_ten_explorers_offered(self):
        choices = self.triggers["workflow_dispatch"]["inputs"]["tool"]["options"]
        self.assertEqual(set(choices), EXPERIMENTAL)

    def test_audit_and_immutability_guards(self):
        for token in ("px_build_readiness audit", "builds_permitted",
                      "git ls-files -s benchmarks", "benchmark tree changed",
                      "readiness.json"):
            self.assertIn(token, self.text)

    def test_reference_isolation_in_workflow(self):
        self.assertNotRegex(self.text, FORBIDDEN)


if __name__ == "__main__":
    unittest.main()

"""PX build plans must stay regenerable, pinned and nonqualifying."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import reference_isolation

from exploratory_builds import plan


def committed():
    return json.loads(plan.PLANS.read_text())


class TestExplorerBuildPlans(unittest.TestCase):
    def setUp(self):
        self.document = committed()
        self.registry, _ = plan._read(plan.REGISTRY)

    def check_mutant(self, change):
        mutated = copy.deepcopy(self.document)
        change(mutated)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "build_plans.json"
            target.write_text(plan.dumps(mutated))
            with self.assertRaises(ValueError):
                plan.validate_document(target, plan.REGISTRY)

    def test_committed_plan_is_byte_identical_to_regeneration(self):
        self.assertEqual(plan.dumps(plan.generate()), plan.PLANS.read_text())

    def test_all_ten_tools_pinned_to_dedicated_adapter_branches(self):
        builds = {row["id"]: row for row in self.document["builds"]}
        self.assertEqual(set(builds), set(plan.EXPERIMENTAL))
        self.assertEqual(
            builds["savage-denovo"]["adapter_branch"], "bench/assembler-savage")
        for tool, row in builds.items():
            candidate = next(x for x in self.registry["candidates"]
                             if x["id"] == tool)
            self.assertEqual(row["adapter_branch"], plan.ADAPTER_BRANCHES[tool])
            self.assertEqual(
                row["adapter_commit"], self.registry["adapter_branch_commits"][tool])
            self.assertEqual(
                row["common_baseline_commit"], self.registry["adapter_baseline_commit"])
            self.assertEqual(row["tool_source_commit"], candidate["source_commit"])
            self.assertEqual(row["tool_source_repo"], candidate["source_repo"])
            self.assertEqual(
                row["image_tag"],
                "localhost/ivanka-exploratory-%s:%s" % (tool, row["adapter_commit"][:12]))
            self.assertTrue(row["nonqualifying"] and row["reference_blind"])
            self.assertFalse(row["qualifying"])

    def test_no_digests_invented_and_no_oci_build_executed(self):
        self.assertTrue(all(row["base_image_digest"] is None
                            and row["tool_binary_sha256"] is None
                            for row in self.document["builds"]))
        self.assertEqual(self.document["policy"]["oci_builds_performed"], 0)
        self.assertEqual(self.document["policy"]["pilots_executed"], 0)
        with mock.patch("subprocess.Popen", side_effect=AssertionError("build")), \
                mock.patch("subprocess.run", side_effect=AssertionError("build")):
            generated = plan.generate()
            plan.validate_document(plan.PLANS, plan.REGISTRY)
            plan.render(generated, "skesa", "sha256:" + "a" * 64,
                        "b" * 64, "/workspace/adapter", str(plan.REGISTRY))

    def test_all_recipes_include_audited_adapter_hashes(self):
        for row in self.document["builds"]:
            with self.subTest(tool=row["id"]):
                args = row["recipe_args"]
                for name in ("MICALL_ADAPTER_COMMANDS_SHA256",
                             "MICALL_ADAPTER_DISPATCH_SHA256"):
                    self.assertEqual(len(args[name]), 64)
                    self.assertIn(name + "=" + args[name],
                                  row["command_template"])
                self.assertFalse(row["build_ready"])
                self.assertTrue(row["blockers"])

    def test_special_tool_build_args_are_present(self):
        by_id = {row["id"]: row for row in self.document["builds"]}
        fermi = by_id["fermi-lite"]
        self.assertIn("TOOL_LICENSE_SHA256", fermi["recipe_args"])
        self.assertEqual(len(fermi["recipe_args"]["TOOL_LICENSE_SHA256"]), 64)
        unicycler = by_id["unicycler"]
        self.assertEqual(
            unicycler["recipe_args"]["SPADES_SOURCE_COMMIT"],
            "896694ce5c7a9050a6ffa9fccc950a4cd9f04363")
        self.assertIn("SPADES_BINARY_SHA256", unicycler["extra_placeholders"])
        self.assertIn("SPADES_BINARY_SHA256={SPADES_BINARY_SHA256}",
                      unicycler["command_template"])

    def test_mutated_adapter_hash_is_rejected(self):
        def change(document):
            document["builds"][0]["recipe_args"][
                "MICALL_ADAPTER_COMMANDS_SHA256"] = "f" * 64
        self.check_mutant(change)

    def test_render_requires_missing_attested_values(self):
        with self.assertRaises(ValueError):
            plan.render(self.document, "unicycler", "sha256:" + "a" * 64,
                        "b" * 64, "/workspace/adapter", str(plan.REGISTRY))
        command = plan.render(
            self.document, "unicycler", "sha256:" + "a" * 64, "b" * 64,
            "/workspace/adapter", str(plan.REGISTRY),
            {"SPADES_BINARY_SHA256": "c" * 64})
        self.assertIn("SPADES_BINARY_SHA256=" + "c" * 64, " ".join(command))

    @unittest.skipUnless(
        Path("/workspace/px-skesa-pqhG00h5412U4gNpP6e2KI-20261121/"
             "attest/skesa").is_file(),
        "local SKESA attestation binary not present")
    def test_skesa_attested_binary_matches_receipt(self):
        import hashlib
        binary = Path("/workspace/px-skesa-pqhG00h5412U4gNpP6e2KI-20261121/"
                      "attest/skesa")
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        skesa = next(row for row in self.document["builds"]
                     if row["id"] == "skesa")
        self.assertEqual(skesa["attested_binary_sha256"], digest)

    def test_resource_policy_matches_frozen_px_contract(self):
        policy = self.document["policy"]
        self.assertEqual(policy["total_incremental_storage_bytes"], 8 * 1024**3)
        self.assertEqual(policy["min_workspace_free_bytes"], 32 * 1024**3)
        self.assertEqual(policy["max_concurrent_exploratory_workers"], 1)
        self.assertEqual(policy["max_container_wall_seconds"], 2400)
        self.assertEqual(policy["max_sampled_process_tree_rss_bytes"], 4_000_000_000)
        self.assertEqual(
            policy["frozen_seven_manifest_sha256"],
            "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f")

    def test_drift_in_pins_is_rejected(self):
        def adapter(document):
            document["builds"][0]["adapter_commit"] = "0" * 40

        def source(document):
            document["builds"][1]["tool_source_commit"] = "1" * 40

        def branch(document):
            document["builds"][2]["adapter_branch"] = "bench/assembler-other"

        def image(document):
            document["builds"][3]["image_tag"] = "localhost/ivanka-micall-iva:base"

        def baseline(document):
            document["builds"][4]["common_baseline_commit"] = "2" * 40

        for change in (adapter, source, branch, image, baseline):
            with self.subTest(change=change.__name__):
                self.check_mutant(change)

    def test_qualification_or_reference_leak_is_rejected(self):
        def digest(document):
            document["builds"][0]["tool_binary_sha256"] = "a" * 64

        def qualifying(document):
            document["builds"][0]["qualifying"] = True

        def promote(document):
            document["builds"][0]["status"] = "image-pinned"

        def reference(document):
            document["builds"][0]["command_template"].append("--reference")

        def hxb2(document):
            document["builds"][0]["command_template"].append("hxb2.fasta")

        def frozen(document):
            document["policy"]["frozen_seven_manifest_sha256"] = "b" * 64

        def roster(document):
            document["builds"].append(copy.deepcopy(document["builds"][0]))

        for change in (digest, qualifying, promote, reference, hxb2,
                       frozen, roster):
            with self.subTest(change=change.__name__):
                self.check_mutant(change)

    def test_launcher_bounds_cannot_be_relaxed(self):
        def detached(document):
            document["builds"][0]["command_template"].insert(-1, "--detach")

        def reservation(document):
            command = document["builds"][0]["command_template"]
            command[command.index("--reserve-bytes") + 1] = str(8 * 1024**3)

        def workers(document):
            document["policy"]["max_concurrent_exploratory_workers"] = 2

        for change in (detached, reservation, workers):
            with self.subTest(change=change.__name__):
                self.check_mutant(change)

    def test_render_requires_real_digests_and_resolves_placeholders(self):
        with self.assertRaises(ValueError):
            plan.render(self.document, "skesa", "not-a-digest", "b" * 64,
                        "/workspace/adapter", str(plan.REGISTRY))
        with self.assertRaises(ValueError):
            plan.render(self.document, "skesa", "sha256:" + "a" * 64, "short",
                        "/workspace/adapter", str(plan.REGISTRY))
        command = plan.render(self.document, "skesa", "sha256:" + "a" * 64,
                              "b" * 64, "/workspace/adapter", str(plan.REGISTRY))
        joined = " ".join(command)
        self.assertNotIn("{", joined)
        self.assertNotIn("--detach", command)
        self.assertIn("sha256:" + "a" * 64, joined)
        self.assertIn("b" * 64, joined)
        self.assertIn(str(plan.REGISTRY), command)

    def test_reference_isolation_guard_accepts_the_build_plans(self):
        self.assertEqual(reference_isolation.check_repository(), [])


if __name__ == "__main__":
    unittest.main()

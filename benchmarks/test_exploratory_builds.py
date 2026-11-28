"""PX build plans must stay regenerable, pinned and nonqualifying."""
import copy
import hashlib
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

    def test_promoted_private_rows_do_not_invalidate_build_templates(self):
        promoted = copy.deepcopy(self.registry)
        skesa = next(c for c in promoted["candidates"] if c["id"] == "skesa")
        skesa["status"] = "image-pinned"
        skesa["image_sha256"] = "a" * 64
        skesa["image_evidence"] = {"path": "/private/image.json", "sha256": "c" * 64}
        promoted["adapter_branch_commits"]["skesa"] = "b" * 40
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "private-registry.json"
            target.write_text(json.dumps(promoted))
            with mock.patch("assembler_bench.exploratory_policy.verified_receipt",
                            return_value=True):
                document = plan.generate(target)
                plan.validate(document, target)
        row = next(r for r in document["builds"] if r["id"] == "skesa")
        self.assertEqual(row["status"], "source-pinned")

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
                row["common_baseline_commit"],
                plan.BASELINES.get(tool, self.registry["adapter_baseline_commit"]))
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
                names = (("BENCHMARK_ASSEMBLER_SHA256", "BENCHMARK_TEST_SHA256")
                         if row["id"] == "unicycler" else
                         ("MICALL_ADAPTER_COMMANDS_SHA256",
                          "MICALL_ADAPTER_DISPATCH_SHA256"))
                for name in names:
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
        self.assertEqual(unicycler["adapter_branch"],
                         "bench/minimal-8458f9e5-unicycler-20261123")
        self.assertEqual(unicycler["common_baseline_commit"],
                         "8458f9e5d34c39a6694b1fb6a40e055d7ce89553")
        self.assertEqual(unicycler["recipe"], "Containerfile.assembler-bench")
        for token in ("ASSEMBLER_TOOL_IMAGE={ASSEMBLER_TOOL_IMAGE}",
                      "TOOL_IMAGE_ID={TOOL_IMAGE_ID}",
                      "MICALL_BASE_COMMIT=8458f9e5d34c39a6694b1fb6a40e055d7ce89553",
                      "MICALL_SOURCE_COMMIT="
                      "5ad7874fe193043fa378063efc123018bff546da"):
            self.assertIn(token, unicycler["command_template"])

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
            self.document, "unicycler", None, None,
            "/workspace/adapter", str(plan.REGISTRY),
            {"ASSEMBLER_TOOL_IMAGE": "sha256:" + "c" * 64,
             "TOOL_IMAGE_ID": "d" * 64})
        joined = " ".join(command)
        self.assertIn("ASSEMBLER_TOOL_IMAGE=sha256:" + "c" * 64, joined)
        self.assertIn("TOOL_IMAGE_ID=" + "d" * 64, joined)
        self.assertNotIn("FORK_BASE_IMAGE", joined)

    def test_unicycler_frozen_lineage_has_no_stale_donor_ancestry(self):
        row = next(r for r in self.document["builds"] if r["id"] == "unicycler")
        blob = json.dumps(row, sort_keys=True)
        self.assertEqual(row["adapter_branch"],
                         "bench/minimal-8458f9e5-unicycler-20261123")
        self.assertEqual(row["adapter_commit"],
                         "5ad7874fe193043fa378063efc123018bff546da")
        self.assertEqual(row["common_baseline_commit"],
                         "8458f9e5d34c39a6694b1fb6a40e055d7ce89553")
        self.assertEqual(row["recipe"], "Containerfile.assembler-bench")
        for stale in ("eeca0381808a6e9ba5ef791c80238a0e2940abb0",
                      "fada133c16ca2c58d60f3cb5ad06eb65565a440d",
                      "2ae4983fcbe30e57e85d0bc6acd464084d57c3e9",
                      "Dockerfile.assembler-bench", "MICALL_FORK_SOURCE_COMMIT"):
            self.assertNotIn(stale, blob)

    def test_frozen_unicycler_lineage_is_validated_from_pinned_file_bytes(self):
        lineage = json.loads(plan.FROZEN_LINEAGE.read_text())
        self.assertEqual(lineage["adapter_repo"],
                         "https://github.com/ottojung/MiCall.git")
        self.assertEqual(lineage["adapter_parent"], lineage["clinical_master"])
        self.assertEqual(lineage["donor_evidence_parent"],
                         lineage["adapter_commit"])
        self.assertEqual(lineage["donor_evidence_commit"],
                         "c16a2f1189ec2056e7c1fd027cd2dddb7cf5c278")
        fixtures = (plan.FROZEN_LINEAGE.parent / "fixtures" / "frozen-unicycler")
        for name, expected in lineage["staged_file_sha256"].items():
            with self.subTest(file=name):
                blob = (fixtures / name).read_bytes()
                self.assertEqual(hashlib.sha256(blob).hexdigest(), expected)
        recipe = (fixtures / "Containerfile.assembler-bench").read_text()
        self.assertIn("FROM $ASSEMBLER_TOOL_IMAGE", recipe)
        self.assertIn("rm -rf /opt/micall "
                      "/opt/venv/lib/python3.12/site-packages/micall", recipe)
        self.assertIn("--reinstall-package micall", recipe)
        for label in ("frozen-upstream-master", "native-tool-image",
                      "integration-mode"):
            self.assertIn(label, recipe)
        row = next(r for r in self.document["builds"] if r["id"] == "unicycler")
        args = row["recipe_args"]
        staged = lineage["staged_file_sha256"]
        self.assertEqual(args["BENCHMARK_ASSEMBLER_SHA256"],
                         staged["benchmark_assembler.py"])
        self.assertEqual(args["BENCHMARK_TEST_SHA256"],
                         staged["test_benchmark_assembler.py"])
        self.assertEqual(args["CONTAINERFILE_SHA256"],
                         staged["Containerfile.assembler-bench"])
        self.assertEqual(args["DEPENDENCY_DONORS_SHA256"],
                         staged["DEPENDENCY-DONORS.md"])
        self.assertIsNone(lineage["spades_core_sha256"])
        self.assertIsNone(lineage["donor_image_id"])
        self.assertIsNone(lineage["final_image_sha256"])

    def test_frozen_unicycler_canary_plan_matches_live_guard_contract(self):
        from assembler_bench.exploratory_runtime import pilot

        canary = json.loads(
            (plan.HERE / "frozen_unicycler_canary_plan.json").read_text())
        lineage = json.loads(plan.FROZEN_LINEAGE.read_text())
        self.assertEqual(canary["lineage_commit"], lineage["adapter_commit"])
        self.assertEqual(canary["donor_evidence_commit"],
                         lineage["donor_evidence_commit"])
        self.assertEqual(canary["forbidden_podman_flags"],
                         list(pilot.FORBIDDEN))
        self.assertEqual(canary["forbidden_cidfile_prefix"], "--cidfile")
        self.assertIn("--cidfile", canary["required_native_flags"])
        self.assertEqual(canary["required_native_flags"][1],
                         "--memory=%d" % pilot.RAM_LIMIT)
        self.assertEqual(canary["reserve_bytes"], plan.RESERVE_BYTES)
        self.assertEqual(canary["min_workspace_free_bytes"], 32 * 1024**3)
        self.assertEqual(canary["max_wall_seconds"], 2400)
        self.assertEqual(canary["max_sampled_process_tree_rss_bytes"],
                         4_000_000_000)
        self.assertEqual(canary["canaries"], {"physical": 1, "synthetic": 1})
        self.assertIsNone(canary["final_image_sha256"])
        self.assertFalse(canary["qualifying"])

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
        self.assertNotIn("total_incremental_storage_bytes", policy)
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

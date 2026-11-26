#!/usr/bin/env python3
"""Read-only verification of PX remaining-tool admission readiness (2026-11-26).

No build, no container, no pilot, no lock, no registry/receipt/frozen mutation.
Run: python3 verify_px_admission_readiness.py
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
CAMPAIGN = Path("/workspace/ivanka-exploratory-ten-20261121")
CACHE = CAMPAIGN / "dependency-evidence-cache-20261125"
HANDOFF = CAMPAIGN / "handoff/px-three-tool-sourcing-20261125.json"
FORK = Path("/workspace/micall-fork-assembler-integration-20261112")
DEPLOYED = Path("/workspace/ivanka-px-superseded-retention-20261126")
EXACT_HEAD = "c245a574182729ba112e9b63329c23c032d91932"
PENGUIN_TAG = "localhost/ivanka-exploratory-penguin:frozen-8458f9e5-8e7c55a3"
PENGUIN_ID = "458ff3d095ecf7db1b3622b56dafb9eec0947f2c3e567fcc3da3ea69f7dba924"

DONOR_HASHES = {
    "Python-2.7.18.tgz": "da3080e3b488f648a3d7a4560ddee895284c3380b11d6de75edb986526b9a814",
    "cpython-v2.7.18.tar.gz": "aa3822dc1615ccaf88352f1c4f2e5687d708be9a45c4c1c93cec64ee123dbec7",
    "scipy-1.2.3.tar.gz": "ecbe6413ca90b8e19f8475bfa303ac001e81b04ec600d17fa7f816271f7cca57",
    "spades-v3.15.5.tar.gz": "9848b69a3a6bab4621eb82b71cac6ed96b111c4109c754e283596e9fa3184b1b",
}

NEW_RECIPES = {
    "penguin": HERE / "Dockerfile.assembler-bench.penguin.corrected",
    "savage": HERE / "Dockerfile.assembler-bench.savage.corrected",
    "unicycler": HERE / "Dockerfile.assembler-bench.unicycler.corrected",
    "savage-donor": HERE / "Dockerfile.assembler-bench.savage.donor-pinned.corrected",
}
ORIGINALS = {
    "penguin": Path("/workspace/micall-px-adapter-penguin-wgavDe3VyQTz2BzGyb7XpS/Dockerfile.assembler-bench"),
    "savage": Path("/workspace/micall-px-adapter-savage-wgavDe3VyQTz2BzGyb7XpS/Dockerfile.assembler-bench"),
    "unicycler": Path("/workspace/micall-px-adapter-unicycler-20261121/Dockerfile.assembler-bench"),
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def noncomment(text):
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


def git_show(path, rev):
    return subprocess.run(["git", "-C", str(path), "show", rev],
                          capture_output=True, text=True, check=True).stdout


class Readiness(unittest.TestCase):
    def test_01_frozen_originals_untouched(self):
        # The two staged copies keep the stray-brace defect; the Unicycler copy
        # keeps the wrong-artifact hash assertion. New files live only here.
        for tool in ("penguin", "savage"):
            with self.subTest(tool=tool):
                self.assertIn("}}", ORIGINALS[tool].read_text())
        self.assertIn('echo "${TOOL_BINARY_SHA256}  /opt/spades/bin/spades-core"',
                      ORIGINALS["unicycler"].read_text())

    def test_02_new_recipes_no_stray_braces_and_keep_pin_guards(self):
        for tool, path in NEW_RECIPES.items():
            with self.subTest(tool=tool):
                text = path.read_text()
                self.assertNotIn("}}", text)
                body = noncomment(text).lower()
                self.assertIn("arg fork_base_image", body)
                self.assertIn("from ${fork_base_image}", body)
                for arg in ("MICALL_FORK_SOURCE_COMMIT", "MICALL_FORK_BASE_COMMIT",
                            "TOOL_SOURCE_COMMIT"):
                    self.assertIn('test "${#%s}" -eq 40' % arg.lower(), body)
                self.assertIn('test "${#tool_binary_sha256}" -eq 64', body)
                for forbidden in ("--ref", "--count_strains", "truth", "seed"):
                    self.assertNotIn(forbidden, body)

    def test_03_unicycler_hash_misapplication_fixed(self):
        text = noncomment((HERE / "Dockerfile.assembler-bench.unicycler.corrected").read_text())
        self.assertIn('echo "${TOOL_BINARY_SHA256}  /opt/Unicycler/unicycler/cpp_functions.so"',
                      text)
        self.assertNotIn('echo "${TOOL_BINARY_SHA256}  /opt/spades/bin/spades-core"', text)
        self.assertIn('echo "${SPADES_CORE_SHA256}  /opt/spades/bin/spades-core"', text)
        self.assertIn('test -n "${SPADES_CORE_SHA256}"', text)
        self.assertIn("test \"${#spades_source_commit}\" -eq 40", text.lower())

    def test_04_savage_donor_pinned_recipe(self):
        text = noncomment((HERE / "Dockerfile.assembler-bench.savage.donor-pinned.corrected").read_text())
        self.assertNotIn("python2.7 python-scipy", text)
        for needle in (DONOR_HASHES["Python-2.7.18.tgz"],
                       DONOR_HASHES["scipy-1.2.3.tar.gz"],
                       "e5cf3fdf13401885e8eea8170624ec96225e2174eb0c611c6f26dd33b489e3ff",
                       "4b41a2badc29877c28a0e903fe7df29a6666a220"):
            with self.subTest(needle=needle[:16]):
                self.assertIn(needle, text)
        self.assertIn("numpy-1.16.6.zip", text)
        self.assertIn("sha256sum -c -", text)
        self.assertIn("/opt/python27/bin/python2.7", text)
        self.assertIn("import numpy; assert numpy.__version__ == '1.16.6'", text)
        self.assertIn("import scipy; assert scipy.__version__ == '1.2.3'", text)
        self.assertIn("bin/ViralQuasispecies", text)
        # The donor host-built binary hash must NOT be asserted on a rebuild.
        self.assertNotIn('echo "${VIRAL_QUASISPECIES_SHA256}', text)
        self.assertIn('echo "${VIRAL_QUASISPECIES_BUILD_SHA256}', text)
        self.assertIn('echo "${QC_BINARIES_BUILD_SHA256}', text)
        self.assertIn('test -n "${VIRAL_QUASISPECIES_BUILD_SHA256}"', text)
        self.assertIn("git rev-parse HEAD:quick-cliques", text)
        self.assertIn("quick-cliques/bin/qc", text)

    def test_10_numpy_attestation_official_and_independent(self):
        data = json.loads((HERE / "numpy_1_16_6_attestation.json").read_text())
        official = data["official_pinned_release_metadata"]
        independent = data["independent_verification"]
        self.assertEqual(official["sha256"],
                         "e5cf3fdf13401885e8eea8170624ec96225e2174eb0c611c6f26dd33b489e3ff")
        self.assertEqual(independent["computed_sha256"], official["sha256"])
        self.assertEqual(independent["computed_md5"], official["md5"])
        self.assertEqual(independent["computed_size_bytes"], data["artifact_size_bytes"])
        self.assertTrue(independent["metadata_match"])
        # Compare against the retained external PyPI metadata artifact, not
        # merely against hardcoded constants in this file.
        ext = json.loads((HERE / "numpy_1_16_6_pypi_metadata.json").read_text())
        sdist = next(x for x in ext["urls"] if x["filename"] == "numpy-1.16.6.zip")
        self.assertEqual(sdist["digests"]["sha256"], official["sha256"])
        self.assertEqual(sdist["digests"]["md5"], official["md5"])
        self.assertEqual(sdist["size"], data["artifact_size_bytes"])
        self.assertEqual(independent["computed_sha256"], sdist["digests"]["sha256"])
        self.assertEqual(independent["retained_official_metadata"],
                         "numpy_1_16_6_pypi_metadata.json")
        self.assertIn("2.7", data["compatibility"]["cpython"])
        self.assertIn("numpy (>=1.8.2)", data["compatibility"]["scipy"])
        self.assertTrue(data["compatibility"]["numpy_1_16_6_satisfies_scipy_requirement"])
        self.assertFalse(data["donor_cache_state"]["numpy_archive_present"])

    def test_11_savage_runtime_pin_compatibility(self):
        src = Path("/workspace/ivanka-px-runtime-an0RVJXx-20261124/src-haploconduct")
        self.assertEqual(
            subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"],
                           capture_output=True, text=True, check=True).stdout.strip(),
            "24e4d9fc35ef6a93e336949a9a8f98ed4ceef362")
        dispatch = (src / "haploconduct.py").read_text()
        self.assertIn("bin/ViralQuasispecies --help", dispatch)
        self.assertIn("'{}/savage.py'.format(base_path)", dispatch)
        makefile = (src / "makefile").read_text()
        self.assertIn("EXEC_NAMES = ViralQuasispecies", makefile)
        self.assertIn("ln -sf haploconduct.py haploconduct", makefile)
        self.assertTrue((src / "savage.py").is_file())
        recipe = (HERE / "Dockerfile.assembler-bench.savage.donor-pinned.corrected").read_text()
        self.assertIn('exec /opt/python27/bin/python2.7 /opt/savage/haploconduct savage "$@"', recipe)

    def test_05_donor_archives_match_pinned_hashes(self):
        for name, expected in DONOR_HASHES.items():
            with self.subTest(archive=name):
                path = CACHE / name
                self.assertTrue(path.is_file(), path)
                self.assertEqual(sha256(path), expected)

    def test_06_handoff_pins_exact(self):
        pins = json.loads(HANDOFF.read_text())["pins"]
        self.assertEqual(pins["frozen_upstream_master"],
                         "8458f9e5d34c39a6694b1fb6a40e055d7ce89553")
        self.assertEqual(pins["frozen_parent_image"],
                         "da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad")
        self.assertEqual(pins["frozen_seven_manifest_sha256"],
                         "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f")
        self.assertEqual(pins["penguin"]["image_sha256"], PENGUIN_ID)
        self.assertIsNone(pins["unicycler"]["image_sha256"])
        self.assertIsNone(pins["savage-denovo"]["image_sha256"])

    def test_07_exact_head_policy_has_no_incremental_ceiling(self):
        src = git_show(DEPLOYED, EXACT_HEAD + ":benchmarks/assembler_bench/exploratory_policy.py")
        for needle in ("32 * 1024**3", "max_concurrent_exploratory_workers\"] != 1",
                       "max_container_wall_seconds\"] != 2400",
                       "max_sampled_process_tree_rss_bytes\"] != 4_000_000_000",
                       "legacy `total_incremental_storage_bytes`"):
            self.assertIn(needle, src)
        self.assertNotIn("total_incremental_storage_bytes\"] <", src)

    def test_08_adapter_cli_contracts_unchanged(self):
        contracts = {
            "8e7c55a3ebcaa4584cb09b1ac743bb5320bd1257": ['ASSEMBLER = "penguin"', '"nuclassemble"'],
            "5ad7874fe193043fa378063efc123018bff546da": ['"unicycler", "-1"', '"-2"'],
            "0919ffa97f609b6f0b650ce834f0fc79822f18e5": ['ASSEMBLER = "savage"', '"-p1"', '"-p2"'],
        }
        for commit, needles in contracts.items():
            with self.subTest(commit=commit[:12]):
                out = git_show(FORK, commit + ":micall/core/benchmark_assembler.py")
                for needle in needles:
                    self.assertIn(needle, out)

    def test_09_penguin_pinned_image_live_in_campaign_store(self):
        podman = shutil.which("podman") or "/var/guix/profiles/per-user/puser/guix-profile/bin/podman"
        if not Path(podman).is_file():
            self.skipTest("podman unavailable")
        env = {"CONTAINERS_STORAGE_CONF": str(CAMPAIGN / "storage.conf"),
               "PATH": "/usr/bin:/bin"}
        out = subprocess.run(
            [podman, "--root", "/workspace/ivanka-exploratory-podman-20261121/store",
             "image", "inspect", PENGUIN_TAG, "--format", "{{.Id}} {{.Size}}"],
            capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr.strip())
        fields = out.stdout.strip().split()
        self.assertEqual(fields[0], PENGUIN_ID)
        self.assertEqual(int(fields[1]), 3348166951)

    def test_12_quick_cliques_source_provenance(self):
        src = Path("/workspace/ivanka-px-runtime-an0RVJXx-20261124/src-haploconduct")
        tree = subprocess.run(
            ["git", "-C", str(src), "rev-parse", "HEAD:quick-cliques"],
            capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(tree, "4b41a2badc29877c28a0e903fe7df29a6666a220")
        # Recompute a content digest of the pinned source tree from git blobs;
        # this is real source provenance, not an invented binary hash.
        names = subprocess.run(
            ["git", "-C", str(src), "ls-tree", "-r", "--name-only", "HEAD:quick-cliques"],
            capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertEqual(len(names), 35)
        h = hashlib.sha256()
        for name in names:
            blob = subprocess.run(
                ["git", "-C", str(src), "show", "HEAD:quick-cliques/" + name],
                capture_output=True, check=True).stdout
            h.update(name.encode() + b"\0" + blob + b"\0")
        self.assertEqual(h.hexdigest(),
                         "2f282f5bd03ab4d9382f304372302e94a2fb933bd3c70e74e7888c6715d7a3fe")
        makefile = (src / "quick-cliques/makefile").read_text()
        for exe in ("printnm", "compdegen", "qc"):
            self.assertIn("$(BIN_DIR)/" + exe, makefile)
        recipe = noncomment((HERE / "Dockerfile.assembler-bench.savage.donor-pinned.corrected").read_text())
        for exe in ("printnm", "compdegen", "qc"):
            self.assertIn("quick-cliques/bin/" + exe, recipe)
        self.assertIn("sha256sum qc printnm compdegen >", recipe)

    def test_13_cli_and_mount_input_contract(self):
        repo = Path("/workspace/px-source-readiness-20261126")
        execution = (repo / "benchmarks/assembler_bench/px_execution.py").read_text()
        pilot = (repo / "benchmarks/assembler_bench/exploratory_runtime/pilot.py").read_text()
        self.assertIn('{_reads_mount(case)}:/reads:ro', execution)
        self.assertIn("assert_reference_blind(argv)", execution)
        self.assertIn('"--network=none"', pilot)
        self.assertIn('RAM_LIMIT = 4_000_000_000', pilot)
        argv_src = execution.split("def micall_argv", 1)[1].split("def assert_reference_blind", 1)[0]
        for flag in ("--ref", "--count_strains", "truth"):
            self.assertNotIn(flag, argv_src)
        adapter = git_show(FORK, "0919ffa97f609b6f0b650ce834f0fc79822f18e5:"
                                 "micall/core/benchmark_assembler.py")
        self.assertIn('OUTPUT_NAME = "contigs_stage_c.fasta"', adapter)
        self.assertIn('"-p1", str(first), "-p2", str(second)', adapter)
        adapter_argv = next(l for l in adapter.splitlines() if l.strip().startswith("argv = ["))
        for flag in ("--ref", "--count_strains", "truth", "seed"):
            self.assertNotIn(flag, adapter_argv)
        recipe = noncomment((HERE / "Dockerfile.assembler-bench.savage.donor-pinned.corrected").read_text())
        self.assertIn('exec /opt/python27/bin/python2.7 /opt/savage/haploconduct savage "$@"', recipe)


if __name__ == "__main__":
    unittest.main(verbosity=2)

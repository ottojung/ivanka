"""Regression tests for reference isolation: deliberately attempt benchmark leakage."""
from pathlib import Path
import tempfile
import unittest

from reference_isolation import (
    ROOT, adapter_contract_errors, assembler_source_errors,
    candidate_source_errors, check_repository, image_recipe_errors,
    image_script_errors,
)


class ReferenceIsolationTests(unittest.TestCase):
    def test_current_repository_is_blind(self):
        self.assertEqual(check_repository(), [])

    def test_pinned_adapter_only_receives_read_pairs(self):
        source = (ROOT / "benchmarks/patch_micall_for_ivanka.py").read_text()
        self.assertEqual(adapter_contract_errors(source), [])

    def test_reference_guided_candidate_is_rejected(self):
        cases = (
            "from ivanka_reference_selector import index_references",
            "def rank(contigs): return build_position_index(references)",
            'score = alignment_score(candidate, reference21)',
            "def rank(x): return hxb2(x)",
            "def choose(): return panel",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertTrue(candidate_source_errors("candidate.py", text))

    def test_reference_agnostic_candidate_is_permitted(self):
        self.assertEqual(candidate_source_errors(
            "candidate.py",
            "def select(contigs): return sorted(contigs, key=len, reverse=True)"
        ), [])

    def test_rust_accepts_read_derived_fasta_seeds(self):
        # These checks follow the module tree rather than assuming one file
        # per operation; the source layout is independent of the contract.
        def module_sources(module):
            directory = ROOT / f"src/assembler/{module}"
            files = directory.rglob("*.rs") if directory.is_dir() else [
                directory.with_suffix(".rs")]
            return "\n".join(path.read_text() for path in files)
        self.assertIn('"--seeds"', module_sources("setup/cli"))
        self.assertIn("fasta_seeds(", module_sources("reads/input"))
        self.assertRegex(module_sources("run"),
                         r"protected_seed_count\s*=\s*contigs\.len\(\)")

    def test_rejects_known_reference_as_seed_producer(self):
        source = 'let known = include_str!("hxb2.fasta");'
        self.assertTrue(assembler_source_errors("src/assembler/run.rs", source))

    def test_rejects_reference_inputs_in_rust(self):
        self.assertTrue(assembler_source_errors(
            "src/assembler/run.rs", 'let hxb2 = include_str!("hxb2.fasta");'
        ))
        self.assertTrue(assembler_source_errors(
            "src/assembler/run.rs", 'let panel = "reference_panel";'
        ))

    def test_rejects_panel_copy_into_assembler_image(self):
        self.assertTrue(image_recipe_errors(
            "Dockerfile", "COPY benchmarks/reference_panel_33.json.gz /usr/local/share/ivanka/"
        ))
        self.assertEqual(image_recipe_errors(
            "Dockerfile", "COPY benchmarks/patch_micall_for_ivanka.py /tmp/patch.py"
        ), [])

    def test_default_adapter_requires_review_before_automatically_forwarding_seeds(self):
        source = (ROOT / "benchmarks/patch_micall_for_ivanka.py").read_text()
        modified = source.replace(
            'subprocess.run(command, check=True, cwd=tmp_dir, env={})',
            'command.extend(["--seeds", str(merged_contigs_csv)])\n'
            '    subprocess.run(command, check=True, cwd=tmp_dir, env={})',
        )
        self.assertTrue(adapter_contract_errors(modified))

    def test_rejects_reference_candidate_in_temporary_repo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "benchmarks").mkdir()
            src = ROOT / "benchmarks/patch_micall_for_ivanka.py"
            (root / "benchmarks/patch_micall_for_ivanka.py").write_text(src.read_text())
            (root / "benchmarks/ivanka_reference_selector.py").write_text(
                "def choose(c, references): return reference_panel(c)"
            )
            self.assertTrue(check_repository(root))

    def test_direct_rust_image_rejects_historical_python_selector(self):
        for script in ("ivanka_read_support_selector.py",
                       "ivanka_trim_unsupported.py",
                       "ivanka_read_tiling.py"):
            recipe = f"COPY benchmarks/{script} /usr/local/bin/{script}"
            self.assertTrue(image_script_errors(
                "benchmarks/Dockerfile.read-backed", recipe, ROOT))

    def test_rust_env_tuning_is_forbidden(self):
        self.assertTrue(assembler_source_errors(
            "src/assembler/some_module.rs", 'let n = std::env::var("IVANKA_BUDGET");'))

    def test_unknown_script_copied_into_image_fails_closed(self):
        for recipe in ("Dockerfile.candidate", "Containerfile.experimental"):
            with self.subTest(recipe=recipe):
                self.assertTrue(image_script_errors(
                    recipe, "COPY benchmarks/mysterious_helper.py /usr/local/bin/ivanka",
                ))

    def test_copy_flags_and_json_form_are_reviewed(self):
        for recipe in (
            "COPY --chown=123 benchmarks/unreviewed.py /tmp/source.py",
            "COPY --chmod=755 --chown=123 benchmarks/unreviewed.py /tmp/source.py",
            'COPY ["benchmarks/unreviewed.py", "/tmp/source.py"]',
            "ADD --chown=123 benchmarks/unreviewed.py /tmp/source.py",
        ):
            with self.subTest(recipe=recipe):
                self.assertTrue(image_script_errors("Containerfile.test", recipe))

    def test_unreviewable_copy_variants_fail_closed(self):
        for recipe in (
            'COPY --chown=100 ["benchmarks/evil.py", "/tmp/evil.py"]',
            "COPY benchmarks/evil.py \\",
        ):
            with self.subTest(recipe=recipe):
                self.assertTrue(image_script_errors("Containerfile.test", recipe))

    def test_copy_flags_do_not_hide_known_candidate_leak(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "benchmarks").mkdir()
            script = root / "benchmarks/ivanka_read_support_selector.py"
            script.write_text("score = alignment_score(reference)")
            self.assertTrue(image_script_errors(
                "Dockerfile",
                "COPY --chown=100 benchmarks/ivanka_read_support_selector.py /tmp/selector.py",
                root,
            ))

    def test_broad_copy_and_containerfile_references_are_rejected(self):
        self.assertTrue(image_script_errors("Containerfile.new", "COPY . /src"))
        self.assertTrue(image_recipe_errors(
            "Containerfile.new",
            "COPY benchmarks/reference_panel_33.json.gz /tmp/panel.gz",
        ))

    def test_stitcher_patch_is_scanned_even_without_selector_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "benchmarks").mkdir()
            src = root / "benchmarks/patch_micall_stitcher_kmer_veto.py"
            src.write_text('def select(contigs): return hxb2(contigs)')
            recipe = "COPY benchmarks/patch_micall_stitcher_kmer_veto.py /tmp/patch.py"
            self.assertTrue(image_script_errors("Dockerfile.candidate", recipe, root))

    def test_approved_build_scripts_exist_and_are_scanned(self):
        recipes = (ROOT / "benchmarks").glob("*")
        for path in recipes:
            if path.name.startswith(("Dockerfile", "Containerfile")):
                with self.subTest(path=path.name):
                    self.assertEqual(image_script_errors(path.name, path.read_text()), [])

    def test_scoring_module_remains_external(self):
        # The evaluator is allowed to load reference panels; the assembler
        # and selection adapter are not.
        self.assertTrue((ROOT / "benchmarks/reference_panel.py").exists())


if __name__ == "__main__":
    unittest.main()

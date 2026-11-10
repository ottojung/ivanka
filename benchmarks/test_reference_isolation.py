"""Regression tests for reference isolation: deliberately attempt benchmark leakage."""
import ast
from pathlib import Path
import tempfile
import unittest

from reference_isolation import (
    ROOT, adapter_contract_errors, assembler_source_errors,
    candidate_source_errors, check_repository, image_recipe_errors,
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

    def test_rust_has_no_auxiliary_fasta_seed_ingress(self):
        native = (ROOT / "src/assembler/setup/cli.rs").read_text()
        self.assertNotIn("--seeds", native)
        self.assertFalse(list((ROOT / "src/assembler").rglob("*.rs"))
                         and any("fasta_seeds(" in p.read_text()
                                 for p in (ROOT / "src/assembler").rglob("*.rs")))

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

    def test_rejects_auxiliary_g2p_input(self):
        source = (ROOT / "benchmarks/patch_micall_for_ivanka.py").read_text()
        modified = source.replace(
            'subprocess.run(command, check=True, cwd=tmp_dir)',
            'command.extend(["--seeds", str(merged_contigs_csv)])\n'
            '    subprocess.run(command, check=True, cwd=tmp_dir)',
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

    def test_scoring_module_remains_external(self):
        # The evaluator is allowed to load reference panels; the assembler
        # and selection adapter are not.
        self.assertTrue((ROOT / "benchmarks/reference_panel.py").exists())


if __name__ == "__main__":
    unittest.main()

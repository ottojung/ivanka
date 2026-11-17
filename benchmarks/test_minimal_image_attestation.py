"""Tests for external (never embedded) minimal-image verification."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from assembler_bench import minimal_image_attestation as check
from assembler_bench import image_source_attestation
from expanded.adapters import ASSEMBLERS

BASE = "a" * 40
REV = "b" * 40
CONTRACT = check.verify_seed_contract
SEED_SOURCE = """\ndef sample_seeds(source,output):\n    return True\ndef assemble(first,second,seeds):\n    argv = ["/usr/local/bin/ivanka", "--reads1", str(first),\n            "--reads2", str(second), "--output", str(output)]\n    if seeds is not None and sample_seeds(seeds, work / "seeds.fasta"):\n        argv.extend(["--seeds", str(work / "seeds.fasta")])\n    subprocess.run(argv,env={})\n"""

class MinimalImageTests(unittest.TestCase):
    def setUp(self):
        patched=patch.object(check,"verify_seed_contract",return_value=True)
        patched.start()
        self.addCleanup(patched.stop)
    def fixture(self, root):
        path = Path(root)
        (path / ".dockerignore").write_text("micall/tests\n")
        (path / "micall/core").mkdir(parents=True)
        (path / "micall/core/benchmark_assembler.py").write_text(SEED_SOURCE)
        (path / "Containerfile.assembler-bench").write_text(
            "FROM immutable-base\nRUN rm -rf /opt/micall\n"
            "COPY micall /opt/micall/micall\n"
            "RUN /opt/uv-home/.local/bin/uv sync --frozen\n"
            "RUN /opt/venv/bin/micall make_blast_db\n")
        return path

    @staticmethod
    def git(*args):
        values = {
            "status": "", "rev-parse": REV,
            "branch": "bench/frozen-8458f9e5-ivanka-20261117",
            "merge-base": BASE,
            "ls-remote": REV + "\trefs/heads/bench/frozen-8458f9e5-ivanka-20261117",
            "diff": "micall/core/denovo.py\nContainerfile.assembler-bench",
        }
        return values[args[1]]

    def test_minimal_branch_is_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.fixture(folder)
            with patch.object(check, "git", side_effect=self.git):
                entry = check.source("ivanka", path, BASE)
        self.assertEqual(entry["source_commit"], REV)

    def test_test_scripts_in_image_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.fixture(folder)
            recipe = path / "Containerfile.assembler-bench"
            recipe.write_text(recipe.read_text() +
                              'RUN /opt/venv/bin/python -c "import micall.core.denovo"\n')
            with patch.object(check, "git", side_effect=self.git):
                with self.assertRaisesRegex(ValueError, "verifier/test"):
                    check.source("ivanka", path, BASE)

    def test_runtime_image_cannot_contain_source_tests(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.fixture(folder)
            (path / ".dockerignore").write_text("*.pyc\n")
            with patch.object(check, "git", side_effect=self.git):
                with self.assertRaisesRegex(ValueError, "source test suite"):
                    check.source("ivanka", path, BASE)

    def test_unrelated_downstream_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.fixture(folder)
            def bad_git(root, *args):
                if args[0] == "diff":
                    return "micall/core/remap.py"
                return self.git(root, *args)
            with patch.object(check, "git", side_effect=bad_git):
                with self.assertRaisesRegex(ValueError, "nonassembler"):
                    check.source("ivanka", path, BASE)

    def test_seed_contract_accepts_only_same_sample_reads(self):
        self.assertTrue(CONTRACT(SEED_SOURCE))
        with self.assertRaisesRegex(ValueError,"command mutation"):
            CONTRACT(SEED_SOURCE.replace('"--seeds"', '"--reference"'))
        with self.assertRaisesRegex(ValueError,"generated same-sample"):
            CONTRACT(SEED_SOURCE.replace('str(work / "seeds.fasta")',
                                         'str("reference.fasta")'))
        with self.assertRaisesRegex(ValueError,"empty child"):
            CONTRACT(SEED_SOURCE.replace("env={}", "env=None"))

    def test_image_identity_and_external_probe(self):
        ident = "f" * 64
        result = {"Id": ident, "Labels": {
            "org.opencontainers.image.source":check.REPO,
            "org.opencontainers.image.revision":REV,
            "org.ottojung.micall.frozen-upstream-master":BASE,
            "org.ottojung.micall.assembler":"ivanka"}}
        def fake_call(argv, **kwargs):
            if argv[1:3] == ["image", "inspect"]:
                return json.dumps([result])
            self.assertEqual(argv[0:2], ["podman","run"])
            self.assertIn("--network=none", argv)
            return '{"installed_source_files":219,"assembler_sha256":"' + ident + '"}'
        with patch.object(check, "call", side_effect=fake_call), patch.object(
                check, "git", return_value=REV):
            proof = check.image("ivanka", ".", ident, BASE)
        self.assertEqual(proof["installed_source_files"], 219)

    def test_live_attestation_dispatch(self):
        images = {name: f"{n+1:x}" * 64 for n,name in enumerate(ASSEMBLERS)}
        roots = {name: "/source/" + name for name in ASSEMBLERS}
        expected = {"schema":check.SCHEMA, "images":{}}
        with tempfile.TemporaryDirectory() as folder:
            files = Path(folder)
            (files/"proof.json").write_text(json.dumps(expected))
            (files/"roots.json").write_text(json.dumps(roots))
            with patch.object(image_source_attestation, "verify_minimal",
                              return_value=expected) as mocked:
                result = image_source_attestation.verify(
                    images,files/"proof.json",files/"roots.json",BASE)
        self.assertEqual(result, expected)
        mocked.assert_called_once_with(images, roots, BASE)

if __name__ == "__main__":
    unittest.main()

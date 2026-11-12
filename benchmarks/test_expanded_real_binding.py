"""Full MiCall competitor adapter binding must never weaken Rust-only Ivanka."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from expanded import run_real
from expanded.adapters import ASSEMBLERS
from expanded.verify_binding import source_hashes
from verify_ivanka_binding import verify_competitor_source
import podman_full_micall as micall


class RealExternalBindingTests(unittest.TestCase):
    def test_only_pinned_reviewed_competitor_sources(self):
        root = Path(__file__).parent / "expanded"
        wrapper = (root / "micall_entrypoint.py").read_bytes()
        helpers = (root / "adapters.py").read_bytes()
        hashes = [hashlib.sha256(x).hexdigest() for x in (wrapper, helpers)]
        for name in ("megahit", "abyss", "spades", "velvet", "haploflow"):
            self.assertEqual(source_hashes(name), tuple(hashes))
            verify_competitor_source(name, name, wrapper, helpers, *hashes)
            with self.assertRaisesRegex(ValueError, "wrong external"):
                verify_competitor_source(name, "ivanka", wrapper, helpers, *hashes)
        with self.assertRaisesRegex(ValueError, "wrong external"):
            verify_competitor_source("ivanka", "ivanka", wrapper, helpers, *hashes)
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            verify_competitor_source("megahit", "megahit",
                                     wrapper + b"altered", helpers, *hashes)

    def test_adapter_cannot_accept_reference_or_tuning_arguments(self):
        root = Path(__file__).parent / "expanded"
        wrapper = (root / "micall_entrypoint.py").read_bytes()
        helpers = (root / "adapters.py").read_bytes()
        changed = wrapper + b'\nparser.add_argument("--reference")\n'
        with self.assertRaisesRegex(ValueError, "unexpected parameters"):
            verify_competitor_source(
                "megahit", "megahit", changed, helpers,
                hashlib.sha256(changed).hexdigest(),
                hashlib.sha256(helpers).hexdigest())

    def test_explicit_binding_only_and_native_default_unchanged(self):
        images = {"ivanka": "b" * 64}
        args = SimpleNamespace(cache_status=False, candidate_assembler="megahit")
        with patch.object(micall, "verify_ivanka_image_binding") as verify:
            micall.verify_execution_image_binding(args, images, images)
            verify.assert_called_once_with("b" * 64, competitor="megahit")
        args.candidate_assembler = None
        with patch.object(micall, "verify_ivanka_image_binding") as verify:
            micall.verify_execution_image_binding(args, images, images)
            verify.assert_called_once_with("b" * 64)
        args.cache_status = True
        with patch.object(micall, "verify_ivanka_image_binding") as verify:
            micall.verify_execution_image_binding(args, images, images)
            verify.assert_not_called()

    def test_real_runner_declares_each_competitor_without_native_overrides(self):
        with TemporaryDirectory() as root_string:
            root = Path(root_string)
            fake_runner = root / "scripts/runner.py"
            fake_runner.parent.mkdir()
            fake_runner.write_text("# pinned test runner")
            images = {name: format(i+1, "064x") for i,name in enumerate(ASSEMBLERS)}
            with (patch.object(run_real, "verify_images"),
                  patch.object(run_real.subprocess, "run",
                               return_value=Mock(returncode=0)) as captured):
                run_real.run(root, root / "results", images, jobs=2,
                             runner=fake_runner)
            self.assertEqual(captured.call_count, 6)
            observed = set()
            for call in captured.call_args_list:
                argv = call.args[0]
                name = next((tool for tool in ASSEMBLERS
                             if images[tool] ==
                             call.kwargs["env"]["IVANKA_IVANKA_IMAGE"]), None)
                if name == "ivanka":
                    self.assertNotIn("--candidate-assembler", argv)
                else:
                    self.assertIn("--candidate-assembler", argv)
                    self.assertEqual(argv[argv.index("--candidate-assembler")+1],
                                     name)
                    observed.add(name)
            self.assertEqual(observed,
                             set(ASSEMBLERS) - {"iva", "ivanka"})


if __name__ == "__main__":
    unittest.main()

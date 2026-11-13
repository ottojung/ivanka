"""Fork-built MiCall images must prove installed code, not merely claim a label."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from assembler_bench import fork_image_attestation as audit
from expanded.adapters import ASSEMBLERS, PROGRAMS


def fake_image(identity, labels, layers, *, assembler=None):
    env = (["MICALL_DENOVO_ASSEMBLER=" + assembler] if assembler else [])
    return {"Id": identity, "RootFS": {"Layers": layers},
            "Config": {"Labels": labels, "Env": env}}


class ForkSourceAndImageAuditTests(unittest.TestCase):
    def test_probe_source_is_well_formed(self):
        code = audit.OCI_PROBE.format(programs=("ivanka",))
        compile(code, "isolated-container-probe", "exec")
        self.assertIn("for name in ('ivanka',):", code)

    def test_only_a_clean_exact_fork_checkout_qualifies(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            for key, value in (("user.name", "Test Source"),
                               ("user.email", "source@example.org")):
                subprocess.run(["git", "-C", str(root), "config",
                                key, value], check=True)
            subprocess.run(["git", "-C", str(root), "remote", "add", "origin",
                            "https://github.com/ottojung/MiCall.git"],
                           check=True)
            folder = root / "micall" / "core"
            folder.mkdir(parents=True)
            for file in audit.FORK_FILES:
                (folder / file).write_text("# source " + file)
            (root / "Dockerfile").write_text("FROM scratch")
            (root / "Dockerfile.assembler-bench").write_text("FROM scratch")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "test"],
                           check=True)
            data = audit.checkout_info(root)
            self.assertEqual(len(data["commit"]), 40)
            self.assertEqual(len(data["source_hashes"]), 4)
            (folder / "denovo.py").write_text("# uncommitted edit")
            with self.assertRaisesRegex(ValueError, "dirty"):
                audit.checkout_info(root)
            subprocess.run(["git", "-C", str(root), "checkout",
                            "--", "micall/core/denovo.py"], check=True)
            subprocess.run(["git", "-C", str(root), "remote", "set-url",
                            "origin", "https://github.com/cfe-lab/MiCall.git"],
                           check=True)
            with self.assertRaisesRegex(ValueError, "canonical"):
                audit.checkout_info(root)

    def _fixtures(self):
        sha = "a" * 40
        source = {"root": "/tmp/nonexistent-fork", "commit": sha,
                  "source_hashes": {f: "f"*64 for f in audit.FORK_FILES},
                  "dockerfile_sha256": "d"*64,
                  "base_dockerfile_sha256": "e"*64}
        base_id = "1"*64
        base_labels = {"org.opencontainers.image.source": audit.SOURCE_REPO,
                       "org.opencontainers.image.revision": sha}
        base = fake_image(base_id, base_labels, ["layer-one","layer-two"])
        images = {}
        info = {"base": base}
        for index, name in enumerate(ASSEMBLERS, start=2):
            identity = str(index)*64
            images[name] = identity
            labels = dict(base_labels,
                          **{"org.ottojung.micall.assembler": name,
                             "org.ottojung.micall.common-base": base_id})
            info[identity] = fake_image(
                identity, labels, ["layer-one","layer-two","extra-"+name],
                assembler=name)
        return source, images, info

    def test_all_seven_binaries_and_installed_modules_are_rechecked(self):
        source, images, all_info = self._fixtures()
        def lookup(ref):return all_info[ref]
        def probe(image, name):
            return {"files": source["source_hashes"], "ivanka_elf": True,
                    "programs": {k: "b"*64 for k in PROGRAMS[name]},
                    "iva_compatible_samtools_sha256": "c"*64}
        with patch.object(audit, "checkout_info", return_value=source), (
                patch.object(audit, "inspect", side_effect=lookup)), (
                patch.object(audit, "_probe", side_effect=probe)):
            result = audit.verify(images, "base", "/tmp/mock-fork")
        self.assertEqual(result["status"],
                         "VERIFIED_BY_INSTALLED_SOURCE_AND_BINARY_SHA")
        self.assertEqual(result["source_url"],
                         "https://github.com/ottojung/MiCall/tree/"+"a"*40)
        self.assertEqual(set(result["images"]), set(ASSEMBLERS))
        self.assertEqual(result["images"]["ivanka"]["assembler"], "ivanka")

    def test_mutable_image_reference_cannot_masquerade_as_digest(self):
        source, images, all_info = self._fixtures()
        images["ivanka"] = "mutable/latest"
        with patch.object(audit, "checkout_info", return_value=source), (
                patch.object(audit, "inspect", side_effect=lambda ref:
                    all_info["2"*64] if ref == "mutable/latest"
                    else all_info[ref])):
            with self.assertRaisesRegex(ValueError, "immutable ID"):
                audit.verify(images, "base", "/tmp/mock")

    def test_spoofed_oci_label_or_changed_source_fails_closed(self):
        source, images, all_info = self._fixtures()
        def probe(image, name):
            return {"files": source["source_hashes"], "ivanka_elf": True,
                    "programs": {k: "b"*64 for k in PROGRAMS[name]},
                    "iva_compatible_samtools_sha256": "c"*64}
        all_info[images["megahit"]]["Config"]["Labels"][
            "org.opencontainers.image.source"] = (
                "https://github.com/cfe-lab/MiCall")
        with patch.object(audit, "checkout_info", return_value=source), (
                patch.object(audit, "inspect", side_effect=all_info.__getitem__)), (
                patch.object(audit, "_probe", side_effect=probe)):
            with self.assertRaisesRegex(ValueError, "source/assembler"):
                audit.verify(images, "base", "/tmp/mock")
        all_info[images["megahit"]]["Config"]["Labels"][
            "org.opencontainers.image.source"] = audit.SOURCE_REPO
        def wrong(image, name):
            value = probe(image, name)
            if name == "abyss":
                value["files"] = dict(value["files"], **{"denovo.py": "0"*64})
            return value
        with patch.object(audit, "checkout_info", return_value=source), (
                patch.object(audit, "inspect", side_effect=all_info.__getitem__)), (
                patch.object(audit, "_probe", side_effect=wrong)):
            with self.assertRaisesRegex(ValueError, "installed MiCall source"):
                audit.verify(images, "base", "/tmp/mock")

    def test_missing_arm_or_nonshared_base_is_rejected(self):
        source, images, info = self._fixtures()
        del images["velvet"]
        with self.assertRaisesRegex(ValueError, "seven"):
            audit.verify(images, "base", "/tmp/mock")
        images["velvet"] = "8"*64
        info["8"*64]["RootFS"]["Layers"][0] = "wrong-layer"
        def probe(image, name):
            return {"files": source["source_hashes"], "ivanka_elf": True,
                    "programs": {k: "b"*64 for k in PROGRAMS[name]},
                    "iva_compatible_samtools_sha256": "c"*64}
        with patch.object(audit, "checkout_info", return_value=source), (
                patch.object(audit, "inspect", side_effect=info.__getitem__)), (
                patch.object(audit, "_probe", side_effect=probe)):
            with self.assertRaisesRegex(ValueError, "base layers"):
                audit.verify(images, "base", "/tmp/mock")


if __name__ == "__main__":
    unittest.main()

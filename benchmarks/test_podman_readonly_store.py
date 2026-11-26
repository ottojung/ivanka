"""Preflight tests for copy-free Podman image reuse."""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from podman_readonly_store import prepare, readback, verify


class ReadOnlyStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "archive"
        self.namespace = self.root / "candidate"
        self.image = "a" * 64
        self.layer = "sha256:" + "b" * 64
        metadata = self.source / "overlay-images"
        self.image_dir = metadata / self.image
        self.image_dir.mkdir(parents=True)
        self.metadata = metadata / "images.json"
        self.metadata.write_text("[]")
        self.raw_manifest = json.dumps({"config": {"digest": "sha256:" + self.image}}).encode()
        (self.image_dir / "manifest").write_bytes(self.raw_manifest)
        self.manifest = hashlib.sha256(self.raw_manifest).hexdigest()
        self.calls = []
        self.readonly = True
        self.graph_root = self.namespace / "store"
        self.image_digest = "sha256:" + self.manifest

    def fake(self, argv, **kwargs):
        self.calls.append(argv)
        self.assertEqual(kwargs["env"]["CONTAINERS_STORAGE_CONF"],
                         str(self.namespace / "storage.conf"))
        self.assertEqual(argv[:2], ["podman", "--remote=false"])
        self.assertTrue(kwargs["check"])
        if argv[2] == "info":
            result = {"store": {"graphRoot": str(self.graph_root),
                                "runRoot": str(self.namespace / "run"),
                                "graphDriverName": "overlay"}}
        elif argv[2] == "images":
            result = [{"Id": self.image, "ReadOnly": self.readonly}]
        elif argv[2:4] == ["image", "inspect"]:
            self.assertEqual(argv[4], self.image)
            result = [{"Id": self.image, "Digest": self.image_digest,
                       "RootFS": {"Layers": [self.layer]}}]
        else:
            self.fail(f"unexpected Podman command {argv}")
        return subprocess.CompletedProcess(argv, 0, json.dumps(result), "")

    def prepare(self):
        return prepare(self.source, self.namespace, self.image, self.manifest, self.fake)

    def verify(self):
        return verify(self.source, self.namespace, self.image, self.manifest, self.fake)

    def test_prepare_and_repeat_preflight(self):
        receipt = self.prepare()
        self.assertEqual(receipt, self.verify())
        self.assertEqual(receipt, json.loads((self.namespace / "reuse-receipt.json").read_text()))
        self.assertEqual(len(self.calls), 6)
        self.assertEqual((self.image_dir / "manifest").read_bytes(), self.raw_manifest)
        self.assertTrue(receipt["podman_read_only"])

    def test_readback_rejects_source_metadata_changed_after_prepare(self):
        self.prepare()
        self.metadata.write_text("[1]")
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            readback(self.source, self.namespace, self.image, self.manifest, self.fake)

    def test_readback_rejects_changed_receipt(self):
        self.prepare()
        (self.namespace / "reuse-receipt.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            readback(self.source, self.namespace, self.image, self.manifest, self.fake)

    def test_existing_namespace_not_overwritten(self):
        self.namespace.mkdir()
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertFalse(self.calls)

    def test_writable_shadow_refused(self):
        self.readonly = False
        with self.assertRaisesRegex(ValueError, "locally writable"):
            self.prepare()
        self.assertFalse((self.namespace / "reuse-receipt.json").exists())

    def test_wrong_graph_root_refused(self):
        self.graph_root = self.source
        with self.assertRaisesRegex(ValueError, "wrong store"):
            self.prepare()

    def test_manifest_pin_refused(self):
        self.image_digest = "sha256:" + "c" * 64
        with self.assertRaisesRegex(ValueError, "differs from pin"):
            self.prepare()

    def test_changed_source_refused(self):
        def changed(argv, **kwargs):
            result = self.fake(argv, **kwargs)
            self.metadata.write_text("[1]")
            return result
        with self.assertRaisesRegex(ValueError, "changed during preflight"):
            prepare(self.source, self.namespace, self.image, self.manifest, changed)

    def test_config_tampering_refused(self):
        self.prepare()
        (self.namespace / "storage.conf").write_text("wrong")
        with self.assertRaisesRegex(ValueError, "configuration differs"):
            self.verify()

    def test_symlink_source_refused(self):
        alias = self.root / "alias"
        alias.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "not symlinked"):
            prepare(alias, self.namespace, self.image, self.manifest, self.fake)

    def test_nested_namespace_refused(self):
        with self.assertRaisesRegex(ValueError, "disjoint"):
            prepare(self.source, self.source / "child", self.image, self.manifest, self.fake)


if __name__ == "__main__":
    unittest.main()

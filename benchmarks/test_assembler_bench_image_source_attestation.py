"""Both attestation formats require a live audit, not trusted JSON labels."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from assembler_bench import image_source_attestation as source


class SourceAttestationDispatchTests(unittest.TestCase):
    def test_independent_dedicated_branches_use_all_pinned_roots(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            attestation = root / "attestation.json"
            branches = root / "branches.json"
            images = {name: f"{n+1:x}" * 64 for n, name in enumerate(
                ("iva", "ivanka", "abyss", "haploflow",
                 "megahit", "spades", "velvet"))}
            roots = {name: "/canonical/" + name for name in images}
            branches.write_text(json.dumps(roots))
            expected = {"schema": source.DEDICATED_SCHEMA, "images": images}
            attestation.write_text(json.dumps(expected))
            with (patch.object(source, "verify_dedicated",
                               return_value=expected) as dedicated,
                  patch.object(source, "verify_shared",
                               side_effect=AssertionError("shared called"))):
                result = source.verify(images, attestation, branches, "base")
            self.assertEqual(result, expected)
            dedicated.assert_called_once_with(images, roots, "base")
            with patch.object(source, "verify_dedicated",
                              return_value={"schema": source.DEDICATED_SCHEMA}):
                with self.assertRaisesRegex(ValueError, "differs"):
                    source.verify(images, attestation, branches, "base")

    def test_shared_commit_only_with_explicit_legacy_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "att.json"
            old = {"schema": source.SHARED_SCHEMA}
            path.write_text(json.dumps(old))
            with patch.object(source, "verify_shared", return_value=old) as old_check:
                self.assertEqual(source.verify({}, path, "/fork", "base"), old)
            old_check.assert_called_once_with({}, "base", "/fork")
            path.write_text(json.dumps({"schema": "unrecognized"}))
            with self.assertRaisesRegex(ValueError, "unsupported"):
                source.verify({}, path, "/fork", "base")


if __name__ == "__main__":
    unittest.main()

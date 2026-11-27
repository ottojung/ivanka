"""PX diagnostics must not execute unpinned or missing MiCall source."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench import px_exact_source as source


class SourceTests(unittest.TestCase):
    def test_unconfigured_is_unavailable(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ImportError, "not configured"):
                source.calculator()

    def test_exact_bytes_and_rejected_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "exact_coverage.py"
            blob = b"def calculate_exact_coverage(): return 42\n"
            path.write_bytes(blob)
            digest = hashlib.sha256(blob).hexdigest()
            with patch.dict(os.environ, {"PX_EXACT_COVERAGE_MODULE": str(path)}), \
                    patch.object(source, "SOURCE_SHA256", digest):
                self.assertEqual(source.calculator()(), 42)
                path.write_bytes(b"raise RuntimeError('must not execute')\n")
                with self.assertRaisesRegex(ImportError, "hash disagrees"):
                    source.calculator()

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "target.py"
            target.write_bytes(b"pass\n")
            link = Path(temp) / "link.py"
            link.symlink_to(target)
            with patch.dict(os.environ, {"PX_EXACT_COVERAGE_MODULE": str(link)}):
                with self.assertRaisesRegex(ImportError, "unavailable"):
                    source.calculator()

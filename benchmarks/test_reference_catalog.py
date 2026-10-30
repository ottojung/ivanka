"""Provenance checks for project-native reference selection."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from reference_catalog import load_micall_projects


class ProjectCatalogTests(TestCase):
    def test_reads_iva_image_only(self):
        data = json.dumps({'projects': {}, 'regions': {}}).encode()
        with patch('reference_catalog.subprocess.check_output', return_value=data) as call, \
             patch.dict(os.environ, {}, clear=True):
            catalog, checksum = load_micall_projects('immutable-iva-image')
        self.assertIn('projects', catalog)
        self.assertEqual(len(checksum), 64)
        command = call.call_args.args[0]
        self.assertIn('immutable-iva-image', command)
        self.assertNotIn('ivanka-image', command)
        self.assertIn('--pull=never', command)

    def test_mismatched_external_catalog_is_rejected(self):
        image_data = json.dumps({'projects': {}, 'regions': {}}).encode()
        with TemporaryDirectory() as folder:
            reference = Path(folder) / 'projects.json'
            reference.write_text('{"projects": {"wrong": {}}, "regions": {}}')
            with patch('reference_catalog.subprocess.check_output', return_value=image_data), \
                 patch.dict(os.environ, {'IVANKA_PROJECTS_JSON': str(reference)}):
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    load_micall_projects('immutable-iva-image')

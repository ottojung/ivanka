"""Provenance checks for project-native reference selection."""
import json
import os
import subprocess
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

    def test_timeout_cleans_exact_named_catalog_container(self):
        with patch('reference_catalog.subprocess.check_output',
                   side_effect=subprocess.TimeoutExpired('podman', 600)) as run, \
             patch('reference_catalog.subprocess.run') as cleanup:
            with self.assertRaisesRegex(RuntimeError, 'removed'):
                load_micall_projects('immutable-iva-image')
        command = run.call_args.args[0]
        self.assertEqual(run.call_args.kwargs['timeout'], 600)
        self.assertIn('--name', command)
        name = command[command.index('--name') + 1]
        self.assertTrue(name.startswith('ivanka-reference-catalog-'))
        self.assertEqual(cleanup.call_args.args[0],
                         ['podman', 'rm', '--force', '--ignore', name])

    def test_cleanup_failure_reports_orphan_name(self):
        with patch('reference_catalog.subprocess.check_output',
                   side_effect=subprocess.CalledProcessError(126, 'podman')), \
             patch('reference_catalog.subprocess.run',
                   side_effect=subprocess.TimeoutExpired('podman rm', 240)):
            with self.assertRaisesRegex(RuntimeError, 'may remain'):
                load_micall_projects('immutable-iva-image')

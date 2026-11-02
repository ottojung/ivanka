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
    def test_detached_source_extraction_preserves_exact_catalog_bytes(self):
        from types import SimpleNamespace
        raw = json.dumps({'projects': {}, 'regions': {}}, sort_keys=True).encode()
        def complete(command, stdout, stderr, remaining):
            self.assertEqual(remaining, 600)
            stdout.write(raw)
            self.assertIn('--pull=never', command)
            self.assertIn('immutable-iva-image', command)
            name = command[command.index('--name') + 1]
            self.assertRegex(name, r'^ivanka-bench-iva-[0-9]+-[0-9]+-[0-9a-f]{8}$')
            return SimpleNamespace(returncode=0, stage='complete')
        with patch.dict(os.environ, {'IVANKA_PODMAN_LIFECYCLE': 'detached'}, clear=True), \
             patch('reference_catalog.run_detached', side_effect=complete) as run, \
             patch('reference_catalog.subprocess.check_output') as legacy:
            catalog, checksum = load_micall_projects('immutable-iva-image')
        self.assertEqual(catalog, {'projects': {}, 'regions': {}})
        self.assertEqual(checksum, __import__('hashlib').sha256(raw).hexdigest())
        legacy.assert_not_called()
        run.assert_called_once()

    def test_detached_catalog_fails_closed_for_uncertain_cleanup(self):
        from types import SimpleNamespace
        with patch.dict(os.environ, {'IVANKA_PODMAN_LIFECYCLE': 'detached'}, clear=True), \
             patch('reference_catalog.run_detached', return_value=SimpleNamespace(
                 returncode=1, stage='remove')):
            with self.assertRaisesRegex(RuntimeError, 'at Podman remove'):
                load_micall_projects('immutable-iva-image')

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

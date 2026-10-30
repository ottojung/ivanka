"""Fail-closed normal-20 full-MiCall qualification tests with synthetic IDs."""
import importlib.util
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'qualification_benchmark', Path(__file__).with_name('podman_full_micall.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Qualification20Tests(unittest.TestCase):
    def execute(self, size=20, qualify=True, mode='both', pinned=True,
                duplicate=False, missing_arm=False, wrong_sample=False,
                missing_reference=False):
        with TemporaryDirectory() as d:
            root = Path(d)
            samples = [f'S{i}' for i in range(size)]
            if duplicate:
                samples[-1] = samples[0]
            (root / 'manifest.tsv').write_text('sample\n' + ''.join(x+'\n' for x in samples))
            (root / 'hxb2.fasta').write_text('>HXB2\nACGT\n')
            results = root / 'results'
            def fake_case(row, *unused, **kwargs):
                record = {'sample': row['sample'], 'status': 'finished',
                          'failed': False, 'total_seconds': 8,
                          'sample_time_limit_seconds': 1200,
                          'best_contig_acceptance': {'pass': True},
                          'project_reference_alignment': {'name': 'example'},
                          'iva': {'exit_code': 0, 'metrics': {}},
                          'riva': {'exit_code': 0, 'metrics': {}}}
                if missing_arm:
                    del record['riva']
                if missing_reference:
                    del record['best_contig_acceptance']
                return record
            argv = ['bench', '--mode', mode]
            if qualify:
                argv.append('--qualify')
            if wrong_sample:
                argv.extend(['--sample', 'S0'])
            env = {'RIVA_EXPECTED_MANIFEST_SHA256': 'pinned'} if pinned else {}
            with patch.object(m, 'DATA', root), patch.object(m, 'RESULTS', results), \
                 patch.object(m, 'image_id', return_value='sha256:fixed'), \
                 patch.object(m, 'verify_identical_micall_base'), \
                 patch.object(m, 'sha', return_value='pinned'), \
                 patch.object(m, 'load_micall_projects', return_value=({'projects':{},'regions':{}},'pinned')), \
                 patch('reference_panel.build_reference_panel',return_value=(('HXB2','ACGT'),('HCV-1a','ACGT'))), \
                 patch.object(m, 'evaluate_sample', side_effect=fake_case), \
                 patch.dict(os.environ, env, clear=True), \
                 patch.object(sys, 'argv', argv):
                error = None
                try:
                    rc = m.main()
                except (ValueError, SystemExit) as exc:
                    rc, error = None, str(exc)
            summaries = list(results.glob('summary-*.json')) if results.exists() else []
            summary = json.loads(summaries[0].read_text()) if summaries else None
            return rc, error, summary

    def test_exact_twenty_two_arm_pinned_is_eligible(self):
        rc, error, summary = self.execute()
        self.assertIsNone(error)
        self.assertEqual(rc, 0)
        self.assertEqual(summary['selected_samples'], 20)
        self.assertEqual(summary['finished_samples'], 20)
        self.assertEqual(summary['accepted_samples'], 20)
        self.assertTrue(summary['full_alpha_pass'])

    def test_unqualified_twenty_does_not_claim_alpha(self):
        rc, _, summary = self.execute(qualify=False)
        self.assertEqual(rc, 0)
        self.assertFalse(summary['full_alpha_pass'])

    def test_missing_manifest_pin_is_rejected(self):
        rc, error, _ = self.execute(pinned=False)
        self.assertIsNone(rc)
        self.assertIn('SHA-256', error)

    def test_nineteen_and_twenty_one_cannot_qualify(self):
        for count in (19, 21):
            with self.subTest(count=count):
                rc, error, _ = self.execute(size=count)
                self.assertIsNone(rc)
                self.assertIn('20', error)

    def test_duplicate_manifest_rejected(self):
        rc, error, _ = self.execute(duplicate=True)
        self.assertIsNone(rc)
        self.assertIn('Duplicate', error)

    def test_qualification_rejects_one_arm_or_sample_filter(self):
        for option in ({'mode': 'riva'}, {'wrong_sample': True}):
            rc, error, _ = self.execute(**option)
            self.assertIsNone(rc)
            self.assertIn('both-arm', error)

    def test_missing_arm_fails_closed_even_if_pass_field_true(self):
        rc, error, summary = self.execute(missing_arm=True)
        self.assertIsNone(error)
        self.assertEqual(rc, 1)
        self.assertFalse(summary['full_alpha_pass'])

    def test_missing_reference_panel_score_fails_closed(self):
        rc, error, summary = self.execute(missing_reference=True)
        self.assertIsNone(error)
        self.assertEqual(rc, 1)
        self.assertFalse(summary['full_alpha_pass'])

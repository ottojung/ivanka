"""Smoke harness tests do not need actual assembler source or private FASTQs."""
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from smoke_rust_assembler_phase import test_binary


class SyntheticRustSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)

    def fake_binary(self, mode):
        # The fake knows synthetic truth ONLY to test the oracle harness.
        # Real Rust Ivanka never receives this file or known phase labels.
        path=self.folder/("fake-"+mode)
        path.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "from pathlib import Path\n"
            "args=sys.argv[1:]\n"
            "def arg(name):return args[args.index(name)+1]\n"
            "t=json.loads((Path(arg('--reads1')).parent/'truth.json').read_text())\n"
            "mode="+repr(mode)+"\n"
            "if mode=='missing':sys.exit(0)\n"
            "chosen=(t['phase_coupled_haplotypes'][0] if mode=='truth' else "
            "t['phase_decoupled_haplotypes'][0])\n"
            "Path(arg('--output')).write_text('>fake\\n'+chosen+'\\n')\n"
        )
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def test_truth_contig_has_real_direct_read_support(self):
        result=test_binary(self.fake_binary('truth'),17,max_pairs=500)
        self.assertEqual(result['unsupported_recombinant_count'],0)
        self.assertGreater(result['original_q15_direct_linked_pairs'],0)
        self.assertEqual(result['contigs'][0]['classification_known_truth'],
                         'consistent_with_source_phase')
        self.assertTrue(result['synthetic_only'])

    def test_recombinant_fails_linked_known_truth_without_claiming_phase(self):
        result=test_binary(self.fake_binary('recombined'),17,max_pairs=500)
        self.assertEqual(result['unsupported_recombinant_count'],1)
        self.assertEqual(result['contigs'][0]['local_original_q15_link'],'unknown')
        self.assertEqual(result['contigs'][0]['classification_known_truth'],
                         'unsupported_recombinant')

    def test_unlinked_opposite_phase_is_unidentifiable(self):
        result=test_binary(self.fake_binary('recombined'),17,max_pairs=500,
                           variant_sites=(280,900))
        self.assertEqual(result['unsupported_recombinant_count'],0)
        self.assertEqual(result['original_q15_direct_linked_pairs'],0)
        self.assertEqual(result['contigs'][0]['classification_known_truth'],
                         'unidentifiable_phase')

    def test_missing_output_or_invalid_controls_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError,'no FASTA'):
            test_binary(self.fake_binary('missing'),17,max_pairs=200)
        for kwargs in ({'max_contigs':0},{'max_pairs':201},
                       {'max_pairs':0},{'max_pairs':True},
                       {'timeout':0}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                test_binary(self.fake_binary('truth'),17,**kwargs)

    def test_cli_strict_flag_fails_when_real_binary_is_mocked_recombinant(self):
        script=Path(__file__).with_name('smoke_rust_assembler_phase.py')
        output=self.folder/'test-report.json'
        command=[sys.executable,str(script),'--binary',
                 str(self.fake_binary('recombined')),
                 '--seeds','17','--max-pairs','500',
                 '--fail-on-recombinant','--output',str(output)]
        run=subprocess.run(command,capture_output=True,text=True,timeout=30)
        self.assertEqual(run.returncode,1,run.stderr)
        report=json.loads(output.read_text())
        self.assertEqual(output.stat().st_mode & 0o777,0o600)
        self.assertEqual(report['known_truth_recombinants_found'],1)
        self.assertFalse(report['real_data_used'])
        self.assertFalse(report['automatic_production_release_permitted'])
        repeated=subprocess.run(command,capture_output=True,text=True,timeout=30)
        self.assertNotEqual(repeated.returncode,0)
        self.assertEqual(json.loads(output.read_text()),report)


if __name__=='__main__':
    unittest.main()

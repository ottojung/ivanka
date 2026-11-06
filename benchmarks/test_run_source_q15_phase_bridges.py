"""Blinded source Q15 bridge diagnostic binds all input content hashes."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from run_source_q15_phase_bridges import source_bound
from synthetic_phase_pairs import generate


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HashBoundPhaseBridgeTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder=Path(tmp.name)
        self.truth=generate(self.folder/'data',variants=(280,480),
                            seed=17,pairs_per_haplotype=100,error_rate=.002)
        self.template=self.folder/'reference.fa'
        self.template.write_text('>synthetic template\n'+
                                 self.truth['phase_coupled_haplotypes'][0]+'\n')
        self.r1=self.folder/'data/synthetic_R1.fastq.gz'
        self.r2=self.folder/'data/synthetic_R2.fastq.gz'
        self.sources=(self.template,self.r1,self.r2)
        self.hashes=tuple(sha(p)for p in self.sources)

    def test_exact_source_hashes_and_only_aggregate_evidence(self):
        report=source_bound(*self.sources,(280,480),self.hashes,max_pairs=200)
        self.assertEqual(report['original_pairs_scanned'],200)
        self.assertGreater(report['original_pairs_with_both_loci_observed'],0)
        self.assertTrue(report['original_qnames_never_serialized'])
        self.assertTrue(report['original_fastq_source_verified_before_and_after'])
        self.assertEqual(report['source_sha256']['reference_fasta'],self.hashes[0])
        self.assertNotIn('synthetic:17:',json.dumps(report))
        self.assertEqual(tuple(sha(p)for p in self.sources),self.hashes)

    def test_cli_writes_private_aggregate_once_outside_sources(self):
        runner=Path(__file__).with_name('run_source_q15_phase_bridges.py')
        separate=tempfile.TemporaryDirectory()
        self.addCleanup(separate.cleanup)
        folder=Path(separate.name)
        output=folder/'links.json'
        args=[sys.executable,str(runner),*(str(path)for path in self.sources),
              '--positions','280','480',
              '--sha256-reference',self.hashes[0],
              '--sha256-r1',self.hashes[1],
              '--sha256-r2',self.hashes[2],
              '--max-pairs','200','--output',str(output)]
        result=subprocess.run(args,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(output.stat().st_mode & 0o777,0o600)
        evidence=json.loads(output.read_text())
        self.assertEqual(evidence['original_pairs_scanned'],200)
        self.assertNotIn('synthetic:17:',output.read_text())
        repeated=subprocess.run(args,capture_output=True,text=True,timeout=20)
        self.assertNotEqual(repeated.returncode,0)
        self.assertEqual(json.loads(output.read_text()),evidence)

    def test_wrong_hash_is_rejected_without_accepting_evidence(self):
        with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):
            source_bound(*self.sources,(280,480),('0'*64,*self.hashes[1:]))
        with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):
            source_bound(*self.sources,(280,480),(self.hashes[0],'0'*64,
                                                   self.hashes[2]))

    def test_multiple_template_sequences_rejected(self):
        self.template.write_text(self.template.read_text()+'>second\nACGT\n')
        new_hashes=(sha(self.template),*self.hashes[1:])
        with self.assertRaisesRegex(ValueError,'Only one pinned'):
            source_bound(*self.sources,(280,480),new_hashes)

    def test_zero_or_unbounded_source_scan_refused(self):
        for count in (0,-1,1000001,True):
            with self.assertRaisesRegex(ValueError,'bounded'):
                source_bound(*self.sources,(280,480),self.hashes,
                             max_pairs=count)


if __name__=='__main__':
    unittest.main()

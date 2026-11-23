"""Independent hash-pinned private remap projection cannot mutate sources."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from run_exact_pair_restoration import source_bound_projection
from sequence_exact_pair_restoration import FIELDS


class SourceBoundProjectionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        before=self.root/'original'
        after=self.root/'candidate'
        before.mkdir()
        after.mkdir()
        self.paths=(before/'remap.csv',before/'references.csv',
                    after/'remap.csv',after/'references.csv')
        ref='ACGTACTTGGGTTAA'
        original=dict(zip(FIELDS,('read1','99','old','2','60','8M',
                                  '=','2','8','CGTACTTG','IIIIIIII')))
        other=dict(original,flag='147')
        candidate=dict(original,rname='new',mapq='9')
        mate=dict(candidate,flag='147')
        for path,rows in ((self.paths[0],[original,other]),
                          (self.paths[2],[candidate,mate])):
            with path.open('w',newline='') as stream:
                writer=csv.DictWriter(stream,FIELDS)
                writer.writeheader()
                writer.writerows(rows)
        for path,data in ((self.paths[1],{'old':ref}),
                          (self.paths[3],{'new':'ACGTACTTGGGTTAC',
                                          'exact':ref})):
            with path.open('w',newline='') as stream:
                writer=csv.writer(stream)
                writer.writerow(('region','sequence'))
                writer.writerows(sorted(data.items()))
        self.digests=tuple(hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in self.paths)

    def test_originals_preserved_output_private_and_identities_not_added(self):
        output=self.root/'separate'/'restored.csv'
        result=source_bound_projection(*self.paths,output,self.digests)
        self.assertEqual(result['original_remap_rows'],2)
        self.assertEqual(result['output_remap_rows'],2)
        self.assertEqual(result['statistics']['restored_original_pairs'],1)
        self.assertEqual(output.stat().st_mode & 0o777,0o600)
        with output.open()as f:
            records=list(csv.DictReader(f))
        self.assertEqual([r['rname'] for r in records],['exact']*2)
        self.assertEqual([r['qname'] for r in records],['read1']*2)
        self.assertEqual([r['mapq'] for r in records],['9']*2)
        self.assertEqual(tuple(hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in self.paths),self.digests)
        with self.assertRaises(FileExistsError):
            source_bound_projection(*self.paths,output,self.digests)

    def test_original_fastq_validates_differently_trimmed_improper_pair(self):
        raw=self.root/'raw'
        raw.mkdir()
        mate_paths=(raw/'R1.fastq',raw/'R2.fastq')
        for i,path in enumerate(mate_paths,1):
            seq='TTTCGTACTTGGAA'
            path.write_text(
                f'@read1/{i}\n{seq}\n+\n'+'I'*len(seq)+'\n')
        path=self.paths[2]
        with path.open('r',newline='') as file:
            rows=list(csv.DictReader(file))
        for i,row in enumerate(rows):
            row.update(flag=str(97 if i==0 else 145),
                       cigar='6M',pos='3',seq='GTACTT',
                       qual='IIIIII')
        with path.open('w',newline='') as file:
            writer=csv.DictWriter(file,FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        digests=tuple(hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in self.paths)
        fastq_hashes=tuple(hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in mate_paths)
        destination=self.root/'separate'/'authenticated-remap.csv'
        result=source_bound_projection(
            *self.paths,destination,digests,
            restore_improper_pairs=True,
            source_fastqs=mate_paths,
            source_fastq_hashes=fastq_hashes)
        self.assertEqual(result['statistics']['improper_original_pairs_restored'],1)
        self.assertEqual(result['statistics']['verified_improper_trimmed_original_pair'],1)
        self.assertTrue(result['original_fastq_source_authenticated'])
        with destination.open() as file:
            projected=list(csv.DictReader(file))
        self.assertEqual([r['flag'] for r in projected],['99','147'])
        self.assertEqual([r['rname'] for r in projected],['exact']*2)
        self.assertEqual(len(projected),len(rows))
        rejected=raw/'forbidden.csv'
        with self.assertRaisesRegex(ValueError,'Original evidence'):
            source_bound_projection(*self.paths,rejected,digests,
                source_fastqs=mate_paths,source_fastq_hashes=fastq_hashes)
        self.assertFalse(rejected.exists())
        damaged=self.root/'separate'/'badfastq.csv'
        with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):
            source_bound_projection(*self.paths,damaged,digests,
                source_fastqs=mate_paths,
                source_fastq_hashes=('0'*64,fastq_hashes[1]))
        self.assertFalse(damaged.exists())

    def test_untrusted_hash_refused_before_creating_output(self):
        output=self.root/'separate'/'tampered.csv'
        with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):
            source_bound_projection(*self.paths,output,('0'*64,*self.digests[1:]))
        self.assertFalse(output.exists())

    def test_no_output_within_any_source_directory(self):
        output=self.paths[2].parent/'additional.csv'
        with self.assertRaisesRegex(ValueError,'Original evidence'):
            source_bound_projection(*self.paths,output,self.digests)
        self.assertFalse(output.exists())


if __name__=='__main__':
    unittest.main()

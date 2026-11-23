"""Original paired FASTQ provenance is exact, quality-aware, and bounded."""
import tempfile
import unittest
from pathlib import Path

from original_fastq_identity import (
    both_alignments_match_original,exact_source_mate,verified_source_pairs)
from snv_q15_evidence import reverse_complement


def record(sequence,qualities):
    return {'seq':sequence,'qual':qualities}


class OriginalFastqIdentityTests(unittest.TestCase):
    def test_exact_trim_and_reverse_complement_with_base_quality_reversal(self):
        original=('GAGTCCACGTTAAA','ABCDEFGHIJKLMN')
        seq=original[0][3:10]
        qual=original[1][3:10]
        self.assertTrue(exact_source_mate(record(seq,qual),original))
        self.assertTrue(exact_source_mate(
            record(reverse_complement(seq),qual[::-1]),original))
        self.assertFalse(exact_source_mate(record(seq,'H'*len(seq)),original))
        self.assertFalse(exact_source_mate(record('*','*'),original))

    def test_verify_both_old_and_new_alignments_against_same_original_pair(self):
        original={1:('AACGTACTTGG','IIIIIIIIIII'),
                  2:('AACGTACTTGG','JJJJJJJJJJJ')}
        old={i:record('CGTACTT',raw[1][2:9])
             for i,raw in original.items()}
        current={i:record('GTACT',raw[1][3:8])
                 for i,raw in original.items()}
        self.assertTrue(both_alignments_match_original(old,current,original))
        current[2]['qual']='IIIII'
        self.assertFalse(both_alignments_match_original(old,current,original))

    def test_source_fastq_target_identity_and_duplicate_qnames(self):
        with tempfile.TemporaryDirectory() as folder:
            first,second=Path(folder)/'r1.fastq',Path(folder)/'r2.fastq'
            def write(names):
                for file,mate in ((first,1),(second,2)):
                    with file.open('w') as stream:
                        for name in names:
                            stream.write(f'@{name}/{mate}\nACGTACGT\n+\nIIIIIIII\n')
            write(['read1','read2'])
            observed=verified_source_pairs(first,second,{'read1'})
            self.assertEqual(observed['read1'][1],('ACGTACGT','IIIIIIII'))
            self.assertNotIn('read2',observed)
            with self.assertRaisesRegex(ValueError,'pair bound'):
                verified_source_pairs(first,second,{'read1'},max_pairs=1)
            write(['read1','read1'])
            with self.assertRaisesRegex(ValueError,'duplicate target'):
                verified_source_pairs(first,second,{'read1'})


if __name__=='__main__':
    unittest.main()

"""Cross-mate phase diagnostics: synthetic tests without private read data."""
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mate_phase_support import audit_mate_phase, fastq_mates, phased_anchors
from contig_diversity import canonical_kmers


def write_fastq(path, records):
    path.write_text(''.join(f'@{name}\n{seq}\n+\n{qual}\n'
                            for name, seq, qual in records))


class MatePhaseSupportTests(unittest.TestCase):
    def test_reverse_complement_and_ambiguity(self):
        rng = random.Random(1901)
        seq = ''.join(rng.choices('ACGT', k=720))
        rc = seq.translate(str.maketrans('ACGT', 'TGCA'))[::-1]
        self.assertEqual(phased_anchors(seq, 31, 320), phased_anchors(rc, 31, 320))
        self.assertEqual(phased_anchors('AAAANNNNCCCC', 4, 4), set())
        self.assertEqual(phased_anchors('ACGT', 31, 4), set())
        with self.assertRaises(ValueError):
            phased_anchors(seq, 0, 12)

    def test_cross_mate_phase_loss_with_all_short_kmers_preserved(self):
        old = 'A' * 70 + 'C' * 70 + 'A' * 70
        new = 'C' * 70 + 'A' * 70 + 'C' * 70
        self.assertEqual(canonical_kmers(old, 11) - canonical_kmers(new, 11), set())
        self.assertEqual(phased_anchors(old, 11, 140) - phased_anchors(new, 11, 140),
                         {('A' * 11, 'A' * 11)})
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / '1.fq', Path(directory) / '2.fq'
            write_fastq(a, [('good/1', 'A' * 40, 'I' * 40),
                            ('low/1', 'A' * 40, '!' * 40),
                            ('another/1', 'A' * 40, 'I' * 40)])
            write_fastq(b, [('good/2', 'T' * 40, 'I' * 40),
                            ('low/2', 'A' * 40, 'I' * 40),
                            ('another/2', 'A' * 40, 'I' * 40)])
            report = audit_mate_phase([old], [new], a, b, 11, [140], 20)
            self.assertEqual(report['sampled_read_pairs'], 3)
            metric = report['distances']['140']
            self.assertEqual(metric['lost_anchor_pairs'], 1)
            self.assertEqual(metric['lost_pairs_observed_in_at_least_1_fastq_pair'], 1)
            self.assertEqual(metric['lost_pairs_observed_in_at_least_3_fastq_pairs'], 0)
            self.assertEqual(metric['maximum_supporting_fastq_pairs'], 2)
            rc = old.translate(str.maketrans('ACGT', 'TGCA'))[::-1]
            retained = audit_mate_phase([old], [rc], a, b, 11, [140], 20)
            self.assertEqual(retained['distances']['140']['lost_anchor_pairs'], 0)

    def test_bad_mate_identity_or_record_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / '1.fq', Path(directory) / '2.fq'
            write_fastq(a, [('one/1', 'ACGT', 'IIII')])
            write_fastq(b, [('two/2', 'ACGT', 'IIII')])
            with self.assertRaisesRegex(ValueError, 'identifiers differ'):
                list(fastq_mates(a, b, 10))
            b.write_text('')
            with self.assertRaisesRegex(ValueError, 'unequal record counts'):
                list(fastq_mates(a, b, 10))
            b.write_text('@one\nACGT\n+\nIII\n')
            with self.assertRaisesRegex(ValueError, 'lengths differ'):
                list(fastq_mates(a, b, 10))
            with self.assertRaises(ValueError):
                list(fastq_mates(a, b, 0))

    def test_cli_and_bad_parameters(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            a, b = root / '1.fq', root / '2.fq'
            old, new = root / 'old.fa', root / 'new.fa'
            old.write_text('>old\n' + 'A'*70 + 'C'*70 + 'A'*70 + '\n')
            new.write_text('>new\n' + 'C'*70 + 'A'*70 + 'C'*70 + '\n')
            write_fastq(a, [('x/1', 'A'*40, 'I'*40)])
            write_fastq(b, [('x/2', 'A'*40, 'I'*40)])
            with self.assertRaises(ValueError):
                audit_mate_phase([], [], a, b, minimum_quality=94)
            with self.assertRaises(ValueError):
                audit_mate_phase([], [], a, b, distances=[0])
            run = subprocess.run(
                [sys.executable, str(Path(__file__).with_name('mate_phase_support.py')),
                 str(old), str(new), str(a), str(b), '--k', '11',
                 '--distances', '140'],
                capture_output=True, text=True, check=True)
            self.assertEqual(
                json.loads(run.stdout)['distances']['140']['maximum_supporting_fastq_pairs'], 1)


if __name__ == '__main__':
    unittest.main()

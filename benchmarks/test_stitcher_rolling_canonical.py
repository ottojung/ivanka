"""Differential tests for the sequence-exact MiCall stitcher k-mer veto."""
import os
import random
import unittest
from pathlib import Path

from patch_micall_stitcher_kmer_veto import patched_source
from test_patch_micall_stitcher_kmer_veto import PatchMiCallStitcherTests

BASE = {"A": 0, "C": 1, "G": 2, "T": 3}

def original_canonical(seq, k):
    complement = str.maketrans('ACGT', 'TGCA')
    ans = set()
    for i in range(max(0, len(seq) - k + 1)):
        window = seq[i:i+k]
        if set(window) <= set(BASE):
            canon = min(window, window.translate(complement)[::-1])
            code = 0
            for c in canon:
                code = code * 4 + BASE[c]
            ans.add(code)
    return frozenset(ans)

def implementation():
    source = patched_source(PatchMiCallStitcherTests.fixture())
    ns = {}
    exec(source[:source.index("\ndef try_combine_1(")], ns)
    return ns

class RollingCanonTest(unittest.TestCase):
    def test_oracle_randomized_with_ambiguous_bases(self):
        func = implementation()["_canonical_kmers_tuple"]
        rng = random.Random(20261101)
        for k in (0, 1, 2, 3, 7, 31):
            for _ in range(450):
                seq = "".join(rng.choices("ACGTNacgt", k=rng.randrange(0, 145)))
                self.assertEqual(func(seq, k), original_canonical(seq, k), (seq, k))

    def test_real_hcv_s87_contigs(self):
        func = implementation()["_canonical_kmers_tuple"]
        fasta_path = os.environ.get("IVANKA_TEST_REAL_STITCHER_FASTA")
        if not fasta_path:
            self.skipTest("Set IVANKA_TEST_REAL_STITCHER_FASTA for real contigs")
        fasta = Path(fasta_path)
        if not fasta.is_file():
            self.skipTest("Authentic S87 contigs not mounted")
        seqs = []
        for line in fasta.read_text().splitlines():
            if line.startswith(">"):
                seqs.append("")
            elif seqs:
                seqs[-1] += line.strip()
        self.assertGreaterEqual(len(seqs), 2)
        for seq in seqs:
            self.assertEqual(func(seq, 31), original_canonical(seq, 31))

    def test_full_veto_equivalence(self):
        ns = implementation()
        fast = ns["preserves_source_kmers"]
        try:
            from micall.utils.exact_coverage import reverse_complement
        except (ImportError, ModuleNotFoundError):
            self.skipTest("MiCall is not installed")
        def original(sources, stitched, k):
            represented = original_canonical(stitched, k)
            for source in sources:
                if len(source) < k:
                    if source not in stitched and reverse_complement(source) not in stitched:
                        return False
                elif not original_canonical(source, k).issubset(represented):
                    return False
            return True
        rng = random.Random(414141)
        for k in (1, 2, 7, 31):
            for _ in range(280):
                seqs = ["".join(rng.choices("ACGTN", k=rng.randrange(0, 100))) for _ in range(3)]
                stitched = "".join(rng.choices("ACGTN", k=rng.randrange(0, 180)))
                self.assertEqual(fast(iter(seqs), stitched, k), original(seqs, stitched, k), (seqs, stitched, k))

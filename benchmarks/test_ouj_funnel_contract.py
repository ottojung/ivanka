"""Hermetic source contract tests for the opt-in funnel-trace feature.

Static only: no cargo, no assembler, no truth, no fixture execution.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALL_SITES = (
    'src/assembler/run/prepare.rs',
    'src/assembler/run/finish.rs',
    'src/assembler/run/read_backed/mod.rs',
)
FEATURE_FILES = (
    'src/assembler/run/funnel/mod.rs',
    'src/assembler/run/funnel/stages.rs',
    'src/assembler/run/funnel/tests.rs',
)


class FunnelContractTests(unittest.TestCase):
    def test_feature_is_opt_in(self):
        text = (ROOT / 'Cargo.toml').read_text()
        self.assertIn('ouj-funnel-trace = []', text)
        self.assertNotIn('default =', text)
        self.assertNotIn('ouj-funnel-trace",', text)

    def test_all_trace_writes_are_feature_gated(self):
        for rel in CALL_SITES:
            lines = (ROOT / rel).read_text().splitlines()
            for n, line in enumerate(lines):
                if 'funnel::emit' not in line:
                    continue
                window = '\n'.join(lines[max(0, n - 3):n])
                self.assertIn('#[cfg(feature = "ouj-funnel-trace")]', window, (rel, n))

    def test_no_raw_sequence_in_published_summary(self):
        text = (ROOT / 'src/assembler/run/funnel/mod.rs').read_text()
        self.assertEqual(text.count('\\"seq\\"'), 1)
        # rustfmt may reflow the write! macro; compare without whitespace so
        # the contract tracks the destination file, not the source layout.
        normalized = ''.join(text.split())
        self.assertIn('write!(private,"{head},\\"seq\\"', normalized)
        self.assertNotIn('write!(summary,"{head},\\"seq\\"', normalized)

    def test_bounds_and_truncation_constants(self):
        text = (ROOT / 'src/assembler/run/funnel/mod.rs').read_text()
        self.assertIn('const MAX_ENTRIES: usize = 32;', text)
        self.assertIn('const MAX_BASES: usize = 65536;', text)
        self.assertIn('.take(MAX_ENTRIES)', text)
        self.assertIn('seq.len().min(MAX_BASES)', text)
        self.assertIn('if seq.len() > MAX_BASES { "t" } else { "f" }', text)

    def test_assembler_side_is_truth_blind(self):
        forbidden = ('hidden-truth', 'manifest.json', 'hxb2', 'panel', 'benchmark')
        for rel in FEATURE_FILES:
            text = (ROOT / rel).read_text().lower()
            for token in forbidden:
                self.assertNotIn(token, text, (rel, token))


if __name__ == '__main__':
    unittest.main()

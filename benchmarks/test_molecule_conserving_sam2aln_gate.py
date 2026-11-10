"""Fail-closed gate: projected hypothesis rows never reach sam2aln/MAX.

The projected remap (with ``|ivanka_hypothesis=`` suffixed duplicate
placements) is an audit-only artifact. Downstream sam2aln/MAX scoring must
consume the exclusive view (original-placement rows only). This suite covers
the integration at the patched sam2aln boundary.
"""
import csv
from pathlib import Path
import tempfile
import unittest

from conserved_pair_remap import (
    derive_exclusive_view,
    project_exclusive_remap,
    project_remap,
    require_molecule_conservation,
    _TARGET_SUFFIX,
)
from patch_micall_conserved_remap import patched_source, LOG_MARKER, INPUT_MARKER

FIELDS = ["qname", "flag", "rname", "pos", "mapq", "cigar",
          "rnext", "pnext", "tlen", "seq", "qual"]


def row(name="read", flag=99, pos=100, rname="1-HCV-1a",
        cigar="100M", seq=None):
    if seq is None:
        seq = "A" * 100
    return dict(qname=name, flag=str(flag), rname=rname, pos=str(pos),
                mapq="0", cigar=cigar, rnext="=", pnext="0", tlen="0",
                seq=seq, qual="I" * len(seq))


def make_csv(path, fields, records):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


class ExclusiveConsumptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.src = self.base / "remap.csv"
        self.refs = self.base / "remap_conseq.csv"
        self.projected = self.base / "projected.csv"
        self.exclusive = self.base / "exclusive.csv"
        seq1 = "A" * 1200
        seq2 = seq1[:600] + "C" + seq1[601:]
        make_csv(self.refs, ["region", "sequence"], [
            {"region": "1-HCV-1a", "sequence": seq1},
            {"region": "2-HCV-1a", "sequence": seq2},
        ])

    def test_exclusive_consumption_keeps_original_prefix_ok(self):
        originals = [row(flag=99), row(flag=147, pos=300)]
        make_csv(self.src, FIELDS, originals)
        before = self.src.read_bytes()
        used, stats = project_exclusive_remap(
            self.src, self.refs, self.projected, self.exclusive)
        # Original byte-identical (prefix_ok).
        self.assertEqual(self.src.read_bytes(), before)
        # Projection audit exists and carries hypothesis duplicates.
        with self.projected.open(newline="") as handle:
            projected_rows = list(csv.DictReader(handle))
        self.assertEqual(len(projected_rows), 4)
        self.assertTrue(any(_TARGET_SUFFIX in r["qname"] for r in projected_rows))
        self.assertEqual(projected_rows[:2], originals)
        # Consumed path is the exclusive view, row-identical to original.
        self.assertEqual(used, self.exclusive)
        with self.exclusive.open(newline="") as handle:
            exclusive_rows = list(csv.DictReader(handle))
        self.assertEqual(exclusive_rows, originals)
        # Fail-closed gate: projected raises, exclusive passes.
        with self.assertRaisesRegex(ValueError, "hypothesis-duplicated"):
            require_molecule_conservation(self.projected)
        self.assertEqual(require_molecule_conservation(self.exclusive), 1)
        self.assertEqual(require_molecule_conservation(self.src), 1)
        self.assertEqual(stats["exclusive_removed_hypothesis_rows"], 2)
        self.assertEqual(stats["consumed_exclusive_path"], str(self.exclusive))
        self.assertFalse(stats["independent_molecules_claimed"])

    def test_no_projection_returns_original_without_audit_copy(self):
        make_csv(self.refs, ["region", "sequence"], [
            {"region": "1-HCV-1a", "sequence": "A" * 1200},
            {"region": "2-HCV-1b", "sequence": "C" * 1200},
        ])
        make_csv(self.src, FIELDS, [row(), row(flag=147)])
        used, stats = project_exclusive_remap(
            self.src, self.refs, self.projected, self.exclusive)
        self.assertEqual(used, self.src)
        self.assertFalse(self.projected.exists())
        self.assertFalse(self.exclusive.exists())
        self.assertIsNone(stats["audit_projected_path"])

    def test_separate_paths_and_empty_base_fail_closed(self):
        make_csv(self.src, FIELDS, [row(), row(flag=147)])
        with self.assertRaisesRegex(ValueError, "separate"):
            project_exclusive_remap(self.src, self.refs, self.src, self.exclusive)
        with self.assertRaisesRegex(ValueError, "separate"):
            derive_exclusive_view(self.src, self.src)
        bad = self.base / "bad.csv"
        make_csv(bad, ["qname"], [{"qname": _TARGET_SUFFIX + "x"}])
        with self.assertRaisesRegex(ValueError, "empty base"):
            derive_exclusive_view(bad, self.exclusive)

    def test_patched_stage_reads_exclusive_never_projected(self):
        import sys
        from types import ModuleType
        from unittest.mock import patch
        originals = [row(flag=99), row(flag=147, pos=300)]
        make_csv(self.src, FIELDS, originals)
        script = ("class Sample:\n"
                  "    def stage(self):\n"
                  "        with_prefix = lambda path: path\n"
                  "        logger = type('Log', (), {'info': lambda *a: None})()\n"
                  + LOG_MARKER + "\n"
                  + "        " + INPUT_MARKER + ":\n"
                  + "            self.text = remap_csv.read()\n")
        import conserved_pair_remap as real
        module = ModuleType("micall.core.ivanka_conserved_remap")
        module.project_exclusive_remap = real.project_exclusive_remap
        package = ModuleType("micall")
        package.__path__ = []
        core = ModuleType("micall.core")
        core.__path__ = []
        ns = {}
        exec(patched_source(script), ns)
        with tempfile.TemporaryDirectory() as d, patch.dict(sys.modules, {
                "micall": package, "micall.core": core,
                "micall.core.ivanka_conserved_remap": module}):
            import shutil
            work = Path(d)
            remap = work / "remap.csv"
            ref = work / "remap_conseq.csv"
            shutil.copyfile(self.src, remap)
            shutil.copyfile(self.refs, ref)
            sample = ns["Sample"]()
            sample.remap_csv = str(remap)
            sample.remap_conseq_csv = str(ref)
            sample.stage()
            # sam2aln input has no hypothesis rows and equals original rows.
            self.assertNotIn("ivanka_hypothesis=", sample.text)
            self.assertIn("qname", sample.text)
            # Audit sidecar was still written for review.
            audit = work / "ivanka-compatible-remap.csv"
            self.assertTrue(audit.exists())
            with audit.open(newline="") as handle:
                audit_rows = list(csv.DictReader(handle))
            self.assertTrue(any(_TARGET_SUFFIX in r["qname"] for r in audit_rows))
            with self.assertRaisesRegex(ValueError, "hypothesis-duplicated"):
                require_molecule_conservation(audit)

    def test_exclusive_output_matches_standalone_diagnostic(self):
        from molecule_conserving_effective_remap import (
            derive_exclusive_view as standalone_derive,
        )
        originals = [row(flag=99), row(flag=147, pos=300)]
        make_csv(self.src, FIELDS, originals)
        _, _ = project_remap(self.src, self.refs, self.projected)
        alt = self.base / "alt-exclusive.csv"
        standalone_derive(self.projected, alt)
        derive_exclusive_view(self.projected, self.exclusive)
        self.assertEqual(self.exclusive.read_bytes(), alt.read_bytes())


if __name__ == "__main__":
    unittest.main()

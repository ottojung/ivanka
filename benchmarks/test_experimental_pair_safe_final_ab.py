"""Synthetic fail-closed tests for MiCall final consensus replay plumbing."""
import csv
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from experimental_pair_safe_final_ab import max_rows, row_multiset, run


class FinalReplayTests(unittest.TestCase):
    def test_max_only_q15(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"conseq.csv"
            p.write_text("region,q-cutoff,consensus-percent-cutoff,sequence\n"
                         "A,15,MAX,XXXX\nA,15,0.25,AAAA\nA,10,MAX,CCCC\n"
                         "B,15,MAX,GGGG\n")
            self.assertEqual(max_rows(p), {"A":"XXXX","B":"GGGG"})

    def test_missing_or_duplicate_max_consensus_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"conseq.csv"
            p.write_text("region,q-cutoff,consensus-percent-cutoff,sequence\n"
                         "S,15,MAX,AAAA\nS,15,MAX,CCCC\n")
            with self.assertRaisesRegex(ValueError,"Repeated final MAX"):
                max_rows(p)
            p.write_text("region,q-cutoff,consensus-percent-cutoff,sequence\n"
                         "S,15,0.25,AAAA\n")
            with self.assertRaisesRegex(ValueError,"No authentic"):
                max_rows(p)

    def test_csv_multiset_preserves_multiplicity_not_row_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,q=Path(tmp)/"a.csv",Path(tmp)/"b.csv"
            p.write_text("a,b\n1,2\n3,4\n1,2\n")
            q.write_text("b,a\n4,3\n2,1\n2,1\n")
            self.assertEqual(row_multiset(p),row_multiset(q))
            q.write_text("b,a\n4,3\n2,1\n")
            self.assertNotEqual(row_multiset(p),row_multiset(q))

    def setup_paths(self, tmp, saved="XXXX", validated=True):
        root=Path(tmp)/"sample"
        scratch=root/"scratch"
        scratch.mkdir(parents=True)
        header="region,q-cutoff,consensus-percent-cutoff,sequence\n"
        (scratch/"conseq.csv").write_text(header+"S,15,MAX,"+saved+"\n")
        for name in ("g2p_aligned.csv","remap_conseq.csv","contigs.csv"):
            (scratch/name).write_text("header\n")
        evidence=Path(tmp)/"evidence"
        evidence.mkdir()
        flags={"replayed_original_exactly":validated,
               "all_original_aligned_records_preserved":True,
               "failure_causes_unchanged":True}
        (evidence/"evidence.json").write_text(json.dumps(flags))
        for arm in ("control","experimental"):
            for suffix in ("aligned.csv","clipping.csv","conseq-ins.csv"):
                (evidence/(arm+"-"+suffix)).write_text("header\n")
        return root,evidence,Path(tmp)/"new-output"

    def test_incomplete_frozen_panel_inputs_rejected_before_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,evidence,target=self.setup_paths(tmp)
            with self.assertRaisesRegex(ValueError,"both frozen reference"):
                run(root,evidence,target,projects_file=Path(tmp)/"projects.json")
            self.assertFalse(target.exists())

    def test_iva_comparison_requires_frozen_panel_and_no_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,evidence,target=self.setup_paths(tmp)
            with self.assertRaisesRegex(ValueError,"IVA comparison requires frozen"):
                run(root,evidence,target,iva_dir=Path(tmp)/"iva")
            self.assertFalse(target.exists())

    def test_reject_unverified_pairing_before_running_aln2counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,evidence,target=self.setup_paths(tmp,validated=False)
            with self.assertRaisesRegex(ValueError,"safety"):
                run(root,evidence,target)
            self.assertFalse(target.exists())

    def test_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,evidence,target=self.setup_paths(tmp)
            target.mkdir()
            with self.assertRaises(ValueError):
                run(root,evidence,target)

    def test_verified_baseline_and_only_candidate_changes(self):
        package=types.ModuleType("micall")
        core=types.ModuleType("micall.core")
        counts=types.ModuleType("micall.core.aln2counts")
        def fake_aln2counts(aligned,nuc,amino,insert,consensus,failed,**kwargs):
            sequence="ACGT" if "experimental" in aligned.name else "XXXX"
            writer=csv.DictWriter(consensus,fieldnames=(
                "region","q-cutoff","consensus-percent-cutoff","sequence"))
            writer.writeheader()
            writer.writerow({"region":"S","q-cutoff":"15",
                             "consensus-percent-cutoff":"MAX","sequence":sequence})
        counts.aln2counts=fake_aln2counts
        modules={"micall":package,"micall.core":core,
                 "micall.core.aln2counts":counts}
        with tempfile.TemporaryDirectory() as tmp,patch.dict("sys.modules",modules):
            root,evidence,target=self.setup_paths(tmp)
            result=run(root,evidence,target)
            self.assertTrue(result["baseline_final_MAX_reproduced_exactly"])
            self.assertEqual(result["regions_changed"]["S"]["bases_changed"],4)
            self.assertTrue(result["candidate_has_more_calls"])
            self.assertEqual((root/"scratch/conseq.csv").read_text().splitlines()[-1],
                             "S,15,MAX,XXXX")
            self.assertTrue((target/"comparison.json").exists())

    def test_baseline_mismatch_blocks_any_candidate_claim(self):
        package=types.ModuleType("micall")
        core=types.ModuleType("micall.core")
        counts=types.ModuleType("micall.core.aln2counts")
        def fake(*args,**kwargs):
            output=args[4]
            output.write("region,q-cutoff,consensus-percent-cutoff,sequence\n"
                         "S,15,MAX,AAAA\n")
        counts.aln2counts=fake
        with tempfile.TemporaryDirectory() as tmp,patch.dict("sys.modules",{
            "micall":package,"micall.core":core,"micall.core.aln2counts":counts}):
            root,evidence,target=self.setup_paths(tmp)
            with self.assertRaisesRegex(AssertionError,"NOT identical"):
                run(root,evidence,target)
            self.assertFalse((target/"comparison.json").exists())


if __name__=="__main__":
    unittest.main()

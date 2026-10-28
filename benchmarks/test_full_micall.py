"""Fast public tests for full MiCall assembler-boundary harness."""
import importlib.util
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

path = Path(__file__).with_name("full_micall.py")
spec = importlib.util.spec_from_file_location("full_micall", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FullMiCallTests(TestCase):
    def test_assembler_filter(self):
        from Bio import SeqIO
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"assembly.fasta"
            p.write_text(">short\n"+"A"*599+"\n>long\n"+"C"*600+"\n")
            self.assertEqual(mod.filter_assembler_contigs(p,600),1)
            with p.open() as f:
                self.assertEqual([len(x) for x in SeqIO.parse(f,"fasta")],[600])

    def test_historical_iva_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            folder=root/"samples"/"TEST"
            folder.mkdir(parents=True)
            (folder/"unstitched_contigs_123.csv").write_text("contig,ref\n"+"A"*605+",seed\n")
            with patch.object(mod,"DATA",root):
                dst=root/"contigs.fasta"
                mod.cached_iva({"sample":"TEST","kive_run_id":"123"},dst)
                self.assertIn("A"*605,dst.read_text())

    def test_best_final_conseq_wins(self):
        iva={"metrics":{"best_hxb2_final_conseq_score":1000}}
        riva={"metrics":{"best_hxb2_final_conseq_score":951}}
        self.assertTrue(mod.acceptance(iva,riva)["pass"])
        riva["metrics"]["best_hxb2_final_conseq_score"]=949
        self.assertFalse(mod.acceptance(iva,riva)["pass"])
        riva["metrics"]["best_hxb2_final_conseq_score"]=None
        self.assertFalse(mod.acceptance(iva,riva)["pass"])

    def test_final_micall_outputs_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/"conseq.csv").write_text("seed,consensus-percent-cutoff,sequence\na,MAX,ACGT\nb,MAX,TTTT\na,0.100,AAAA\n")
            (p/"genome_coverage.csv").write_text("coverage\n0\n12\n8\n")
            m=mod.pipeline_metrics(p,"ACGT")
            self.assertEqual(m["final_conseq_max_count"],2)
            self.assertEqual(m["genome_coverage_nonzero_rows"],2)
            self.assertTrue(m["files"]["conseq.csv"]["exists"])

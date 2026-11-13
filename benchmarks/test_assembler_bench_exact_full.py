"""Exact read placement and both-track publication must match pinned MiCall."""
import csv
import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from assembler_bench.metric_catalog_exact import catalog, explanations, values
from assembler_bench.public_case_metrics import synthetic, physical
from produce_exact_coverage import generate, summarize

SITE = Path(__file__).resolve().parents[1] / "site/bench"


class FullExactCoverageTests(unittest.TestCase):
    def test_summary_preserves_zero_counts_and_quantiles(self):
        data=summarize([0,0,1,2,10,100,0])
        self.assertEqual(data["zero_count"],3)
        self.assertEqual(data["longest_zero_run"],2)
        self.assertEqual(data["breadth_ge_1"],4/7)
        self.assertEqual(data["breadth_ge_100"],1/7)
        self.assertEqual(data["median"],1)
        self.assertEqual(data["quantiles"]["p50"],1)
        self.assertEqual(len(data["depth_profile"]),7)
        self.assertEqual(set(catalog()),set(explanations()))
        self.assertEqual(len(catalog()),34)
        self.assertEqual(catalog()["exact_coverage_breadth_ge_1"][0],
                         "Exact read coverage")

    def test_both_tracks_against_pinned_micall_fixtures(self):
        try:
            from micall.utils.exact_coverage import reverse_complement
        except ImportError:
            self.skipTest("MiCall reference exact_coverage unavailable")
        rng=random.Random(9234)
        genome="".join(rng.choices("ACGT",k=350))
        read1=genome[50:200]
        read2=reverse_complement(genome[170:320])
        damaged=list(genome[100:250])
        damaged[75]="A" if damaged[75]!="A" else "C"
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for i,records in [(1,[read1,"".join(damaged)]),
                              (2,[read2,genome[:100]])]:
                with (root/f"R{i}.fastq").open("w") as stream:
                    for j,seq in enumerate(records):
                        stream.write(f"@r{j}\n{seq}\n+\n{'I'*len(seq)}\n")
            with (root/"conseq.csv").open("w",newline="") as stream:
                writer=csv.DictWriter(stream,fieldnames=[
                    "region","consensus-percent-cutoff","sequence"])
                writer.writeheader()
                writer.writerow({"region":"test","consensus-percent-cutoff":"MAX",
                                 "sequence":genome})
            report=generate(root/"R1.fastq",root/"R2.fastq",
                            root/"conseq.csv",root/"out.csv",overlap_size=70)
            with (root/"out.csv").open() as src:
                rows=list(csv.DictReader(src))
            full=[int(x["exact_coverage"]) for x in rows]
            inner=[int(x["exact_coverage_overlapped"]) for x in rows]
            self.assertEqual(len(full),350)
            self.assertEqual(full[49],1)
            self.assertEqual(full[50],2)
            self.assertEqual(full[190],2)
            self.assertEqual(full[319],1)
            self.assertEqual(full[320],0)
            self.assertEqual(sum(v>0 for v in full),320)
            self.assertEqual(sum(v>0 for v in inner),20)
            self.assertEqual(inner[120],1)
            self.assertEqual(inner[129],1)
            self.assertEqual(inner[130],0)
            self.assertEqual(inner[240],1)
            self.assertEqual(inner[249],1)
            self.assertEqual(inner[250],0)
            self.assertEqual(report["tracks"]["exact_coverage"]
                             ["zero_count"],30)
            self.assertEqual(report["tracks"]["exact_coverage_overlapped"]
                             ["zero_count"],330)
            self.assertEqual(len(values(report)),34)

    def test_multiple_exact_placements_both_strands(self):
        try:
            from micall.utils.exact_coverage import calculate_exact_coverage
        except ImportError:
            self.skipTest("MiCall exact_coverage unavailable")
        import io
        seq="ACGTTTCGA"
        contig=seq+"GGGG"+seq
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for read,i in ((seq,1),("TCGAAACGT",2)):
                (root/f"R{i}.fastq").write_text(
                    f"@read\n{read}\n+\n{'I'*len(read)}\n")
            full,inner,_=calculate_exact_coverage(
                root/"R1.fastq",root/"R2.fastq",
                io.StringIO("ref,sequence\ncase,"+contig+"\n"),70)
            self.assertEqual(int(full["case"][0]),2)
            self.assertEqual(int(full["case"][13]),2)
            self.assertEqual(sum(inner["case"]),0)

    def test_case_measurements_and_no_private_aliases(self):
        sample={"diagnostics":{"ivanka":{"nuc_q15_mean_depth":3.5}},
                "exact_profiles":{"ivanka":{
                    "selected_length":150, "full_span":[2,3],
                    "inner_70":[1,0],
                    "implementation_sha256":"a"*64,
                    "selected_sequence_sha256":"b"*64,
                    "coverage_csv_sha256":"c"*64}}}
        from assembler_bench.public_case_metrics import validate_sample
        with self.assertRaisesRegex(ValueError,"unpinned"):
            validate_sample(sample,("ivanka",))
        sample["exact_profiles"]["ivanka"]["implementation_sha256"] = (
            "3d3b3d38ea83d1a3bb6872ef20cc5a8f1177ee3e6a272c635aa28dd77ba6f4ee")
        validate_sample(sample,("ivanka",))
        for result in (synthetic({"diagnostics":{}}),
                       physical({"metrics":{}})):
            self.assertEqual(result,{})

    def test_browser_consumes_each_individual_numeric_measurement(self):
        node=shutil.which("node")
        if not node:
            self.skipTest("node unavailable")
        source=r"""
const assert=require('node:assert/strict');
global.BenchRanks=require(process.argv[1]);
const subjects=require(process.argv[2]);
const run={
  samples:[{alias:'H001',failures:[],
    diagnostics:{iva:{nuc_q15_mean_depth:1},ivanka:{nuc_q15_mean_depth:3}}},
    {alias:'H002',failures:[],
      diagnostics:{iva:{nuc_q15_mean_depth:3},ivanka:{nuc_q15_mean_depth:4}}},
    {alias:'H003',failures:['iva'],
      diagnostics:{iva:{nuc_q15_mean_depth:100},ivanka:{nuc_q15_mean_depth:8}}}],
  tools:['iva','ivanka'],expected_sample_count:400,cohort:'synthetic'};
const key='nuc_q15_mean_depth',report={expected_samples:400,metrics:{}};
const ranking=BenchRanks.summary(run,null,key,'higher');
assert.equal(ranking[0].tool,'ivanka');
assert.equal(ranking[0].observed,3);
assert.equal(ranking[1].observed,2);
assert.equal(ranking[1].mean,2);
const pairs=BenchRanks.pairs(run,null,key,'higher','ivanka','iva');
assert.equal(pairs.filter(x=>!x.failed).length,2);
const result=subjects.evaluate(report,'ivanka','iva',
    [{key,label:'Q15 depth',direction:'higher'}],null,run);
assert.equal(result.entries[0].paired,2);
assert.equal(result.entries[0].observed.gains,2);
assert.equal(result.entries[0].subset.status,'dominates');
assert.equal(result.entries[0].subset.proof.psi1,1.5);
assert.equal(result.entries[0].subset.proof.psi2,2.5);
assert.equal(subjects.moment(result.entries[0],2).value,2.5);
console.log('ALL_CASE_METRICS_AND_PAIRED_PSI_OK');
"""
        proc=subprocess.run([node,"-e",source,str(SITE/"rankings.js"),
                             str(SITE/"subjects.js")],capture_output=True,
                            text=True,timeout=10)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertIn("ALL_CASE_METRICS_AND_PAIRED_PSI_OK",proc.stdout)


if __name__=="__main__":
    unittest.main()

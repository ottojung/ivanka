"""Pinned, biologically real HIV reference-derived truth invariants."""
import json
from pathlib import Path
import tempfile
import unittest

from expanded.hxb2_cohort import verify_cohort
from expanded.hxb2_truth import (ACCESSIONS, haplotypes, plan, references,
                                 seeded, synthesize, validate)
from expanded.synthetic import FAMILIES, generate_case, generate_cohort


class Hxb2AncestryTests(unittest.TestCase):
    def test_all_pinned_subtypes_reproduce_exact_genbank_sources(self):
        records, digest = references()
        self.assertEqual(set(records), set(ACCESSIONS))
        self.assertEqual(len(digest), 64)
        self.assertEqual(records["K03455.1"].replace("-", ""), "".join(
            x for x in (Path(__file__).parent / "expanded/references/K03455.1.fasta")
            .read_text().splitlines() if not x.startswith(">")))
        self.assertGreater(len(records["K03455.1"].replace("-", "")), 9000)

    def test_random_homologous_recombination_and_uniform_mutations(self):
        records, _ = references()
        for family in FAMILIES:
            for seed in (0, 1, 4):
                genomes, fractions, contaminant, ancestry = haplotypes(
                    family, seed)
                self.assertEqual(len(genomes), len(fractions))
                self.assertTrue(contaminant)
                for i, (sequence, recipe) in enumerate(zip(
                        genomes, ancestry["recipes"])):
                    self.assertEqual(sequence, synthesize(recipe, records))
                    self.assertEqual(recipe["seed"], seeded(family, seed, i))
                    self.assertEqual(recipe["segments"][0]["accession"], "K03455.1")
                    self.assertEqual(recipe["segments"][0]["start"], 0)
                    self.assertEqual(recipe["segments"][-1]["end"],
                                     len(records["K03455.1"]))
                    self.assertTrue(all(x["accession"] in ACCESSIONS
                                        for x in recipe["segments"]))
                    self.assertTrue(set(sequence) <= set("ACGT"))
                    self.assertLessEqual(len(recipe["mutations"]), len(sequence)*.05)
                    sites = [x["site"] for x in recipe["mutations"]]
                    self.assertEqual(len(sites), len(set(sites)))
                    self.assertEqual(recipe, plan(family, seed, i, records))

    def test_generation_and_independent_replay_both_mates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = generate_case(root, "minority_5pct", 8, pairs=40)
            self.assertEqual(a["schema"], "ivanka.expanded.synthetic.hxb2.v1")
            self.assertTrue(validate(root / "minority_5pct-s008"))
            self.assertEqual(a["haplotype_count"], 2)
            self.assertTrue(all(x in a["sha256"] for x in (
                "reads/R1.fastq.gz", "reads/R2.fastq.gz",
                "hidden-truth/haplotypes.fasta")))
            self.assertEqual(a["hxb2_ancestry"]["schema"],
                             "ivanka.expanded.hxb2_ancestry.v1")

    def test_truth_and_ancestry_tampering_fail_even_if_hash_is_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_case(root, "clonal", 4, pairs=30)
            case = root / "clonal-s004"
            truth = case / "hidden-truth/haplotypes.fasta"
            before = truth.read_text()
            seq = list(before.splitlines()[1])
            seq[500] = "C" if seq[500] != "C" else "A"
            truth.write_text(">haplotype_1\n" + "".join(seq) + "\n")
            manifest = json.loads((case / "manifest.json").read_text())
            from expanded.synthetic import fingerprint
            manifest["sha256"]["hidden-truth/haplotypes.fasta"] = fingerprint(truth)
            (case / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "not reproducible"):
                validate(case)
            truth.write_text(before)
            manifest["hxb2_ancestry"]["recipes"][0]["mutations"] = []
            (case / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "ancestry"):
                validate(case)

    def test_mutation_limit_and_bases_are_fail_closed(self):
        records, _ = references()
        recipe = plan("clonal", 1, 0, records)
        source = synthesize(recipe, records)
        recipe["mutations"] = [
            {"site": i, "base": "C" if source[i] != "C" else "A"}
            for i in range(int(len(source) * .05) + 1)]
        with self.assertRaisesRegex(ValueError, "5%"):
            synthesize(recipe, records)
        recipe["mutations"] = [{"site": 50, "base": "N"}]
        with self.assertRaises(ValueError):
            synthesize(recipe, records)

    def test_legacy_random_cohort_cannot_pass_hxb2_preflight(self):
        from expanded.run_synthetic import cohort_rows
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "old"
            generate_cohort(old, seeds=1, pairs=20, historical_random=True)
            with self.assertRaisesRegex(ValueError, "legacy random"):
                list(cohort_rows(old))
            new = Path(tmp) / "hxb2"
            generate_cohort(new, seeds=1, pairs=20)
            self.assertEqual(len(list(cohort_rows(new))), 25)
            self.assertEqual(len(verify_cohort(new, expected=25)), 64)


if __name__ == "__main__":
    unittest.main()

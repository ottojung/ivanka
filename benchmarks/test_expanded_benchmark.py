"""Expanded synthetic diversity, assembler contracts and strict qualification."""
import importlib.util
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from expanded.adapters import (ASSEMBLERS, PROGRAMS, binary_hash,
                               interleave_fastq, require_programs, steps)
from expanded.gate import (BASELINES, SCORE_ORIGINS, TIMING_ORIGIN,
                           TRUTH_SCHEMA, summarize_gate)
from expanded.synthetic import FAMILIES, generate_case, generate_cohort


class ExpandedSyntheticTests(unittest.TestCase):
    def test_reproducible_across_output_directories(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            for family in FAMILIES:
                with self.subTest(family=family):
                    first = generate_case(a, family, 7, pairs=75)
                    second = generate_case(b, family, 7, pairs=75)
                    self.assertEqual(first, second)
                    self.assertTrue(first["truth_is_evaluation_only"])
                    root = Path(a) / f"{family}-s007"
                    for label, digest in first["sha256"].items():
                        self.assertEqual(binary_hash(root / label), digest)

    def test_many_diverse_reproducible_cases(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = generate_cohort(Path(temp) / "cases", seeds=2, pairs=65)
            self.assertEqual(manifest["samples"], 2 * len(FAMILIES))
            self.assertGreaterEqual(manifest["samples"], 40)
            self.assertEqual(len(set(x["id"] for x in manifest["cases"])),
                             manifest["samples"])
            with self.assertRaises(FileExistsError):
                generate_cohort(Path(temp) / "cases", seeds=2, pairs=65)

    def test_true_biological_and_technical_behaviors(self):
        with tempfile.TemporaryDirectory() as temp:
            pcr = generate_case(temp, "pcr_jackpot", 17, pairs=300)
            minor = generate_case(temp, "minority_30pct", 17, pairs=300)
            chimeras = generate_case(temp, "discordant_pairs", 17, pairs=300)
            contamination = generate_case(temp, "contaminated", 17, pairs=300)
            low = generate_case(temp, "low_depth", 17, pairs=300)
            deep = generate_case(temp, "ultradeep", 17, pairs=300)
            self.assertLessEqual(pcr["unique_fragment_coordinates"], 13)
            import gzip
            with gzip.open(Path(temp) / "pcr_jackpot-s017/reads/R1.fastq.gz", "rt") as inp:
                records = inp.readlines()
            # A PCR jackpot has several original inserts, not all reads from
            # one coordinate with accidentally swapped start/insert fields.
            self.assertGreater(len(set(records[i+1] for i in range(0,len(records),4))), 1)
            self.assertEqual(minor["haplotype_count"], 2)
            self.assertTrue(all(x > 0 for x in minor["sampled_haplotype_pairs"]))
            self.assertGreater(chimeras["chimeric_mates"], 0)
            self.assertGreater(contamination["contamination_pairs"], 0)
            self.assertEqual(low["pairs"], 75)
            self.assertEqual(deep["pairs"], 900)

    def test_strand_bias_changes_fragment_orientation(self):
        from expanded.synthetic import rc
        with tempfile.TemporaryDirectory() as temp:
            normal = generate_case(temp, "clonal", 12, pairs=300)
            generate_case(temp, "strand_bias", 12, pairs=300)
            def reverse_fraction(family):
                source = Path(temp) / f"{family}-s012"
                truth = (source / "hidden-truth/haplotypes.fasta").read_text().splitlines()[1]
                reverse = rc(truth)
                with gzip.open(source / "reads/R1.fastq.gz", "rt") as stream:
                    lines = stream.readlines()
                origins = [lines[i+1].strip()[:24] for i in range(0, len(lines), 4)]
                return sum(fragment in reverse for fragment in origins) / len(origins)
            self.assertAlmostEqual(normal["nominal_fractions"][0], 1.0)
            self.assertGreater(reverse_fraction("clonal"), 0.35)
            self.assertLess(reverse_fraction("clonal"), 0.65)
            self.assertLess(reverse_fraction("strand_bias"), 0.2)

    def test_valid_mates_and_hidden_truth(self):
        with tempfile.TemporaryDirectory() as temp:
            for family in FAMILIES:
                with self.subTest(family=family):
                    spec = generate_case(temp, family, 0, pairs=50)
                    folder = Path(temp) / f"{family}-s000"
                    with (gzip.open(folder / "reads/R1.fastq.gz", "rt") as a,
                          gzip.open(folder / "reads/R2.fastq.gz", "rt") as b):
                        first, second = a.readlines(), b.readlines()
                    self.assertEqual(len(first), 4 * spec["pairs"])
                    self.assertEqual(len(first), len(second))
                    for i in range(0, len(first), 4):
                        self.assertEqual(first[i].split("/")[0],
                                         second[i].split("/")[0])
                        for stream in (first, second):
                            self.assertEqual(len(stream[i+1].strip()), 150)
                            self.assertEqual(len(stream[i+3].strip()), 150)
                    self.assertTrue((folder / "hidden-truth/haplotypes.fasta").is_file())


class ExpandedAdapterTests(unittest.TestCase):
    def test_all_seven_use_only_original_reads(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            r1, r2 = root / "reads/R1.fastq.gz", root / "reads/R2.fastq.gz"
            r1.parent.mkdir()
            for path, mate in ((r1, 1), (r2, 2)):
                with gzip.open(path, "wt") as stream:
                    stream.write(f"@x/{mate}\n" + "A"*150 + "\n+\n" + "I"*150 + "\n")
            bins = {}
            for name in ASSEMBLERS:
                bins[name] = {program: {"path": "/bin/true", "sha256": "a"*64}
                              for program in PROGRAMS[name]}
            self.assertEqual(len(ASSEMBLERS), 7)
            for name in ASSEMBLERS:
                with self.subTest(assembler=name):
                    place = root / name
                    place.mkdir()
                    commands, out = steps(name, r1, r2, place, bins)
                    self.assertTrue(commands)
                    self.assertTrue(out.is_relative_to(place))
                    self.assertNotIn("hidden-truth", str(commands))
                    self.assertNotIn("--reference", str(commands))
                    self.assertNotIn("--seeds", str(commands))
            self.assertEqual(len(BASELINES), 6)

    def test_haploflow_receives_both_mates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = generate_case(root, "clonal", 0, pairs=20)
            case = root / "clonal-s000"
            merged = root / "merged.fastq"
            interleave_fastq(case / "reads/R1.fastq.gz",
                             case / "reads/R2.fastq.gz", merged)
            text = merged.read_text()
            self.assertEqual(text.count("\n+\n"), 2*spec["pairs"])
            self.assertTrue(text.startswith("@synthetic:clonal:0:00000000/1"))

    def test_missing_binary_fails_before_comparison(self):
        with self.assertRaises(FileNotFoundError):
            require_programs(paths={x: "/missing/never" for programs in
                                   PROGRAMS.values() for x in programs})


class ExpandedGateTests(unittest.TestCase):
    @staticmethod
    def sample(name, cohort, family=None):
        results = {}
        for tool in ASSEMBLERS:
            results[tool] = {
                "status": "success", "sha256": "a"*64,
                "seconds": 1 if tool == "ivanka" else 2,
                "score": 120 if tool == "ivanka" else 100,
                "score_origin": SCORE_ORIGINS[cohort],
                "timing_origin": TIMING_ORIGIN,
            }
        provenance = ({
            "schema": TRUTH_SCHEMA, "valid": True,
            "cohort_sha256": "c"*64,
            "verification_sha256": "d"*64,
        } if cohort == "synthetic" else None)
        return {"id": name, "cohort": cohort, "family": family,
                "input_sha256": "b"*64, "truth_validation": provenance,
                "results": results}

    def cases(self):
        return [self.sample("real-1", "real"),
                self.sample("clonal-1", "synthetic", "clonal")]

    def qualified(self, records):
        return summarize_gate(records, real_count=1,
                              synthetic_seeds=1, families=("clonal",))

    def test_every_competitor_must_be_beaten_on_both_cohorts(self):
        result = self.qualified(self.cases())
        self.assertTrue(result["pass"], result["errors"])
        self.assertEqual(set(result["comparisons"]["real"]), set(BASELINES))
        self.assertEqual(set(result["comparisons"]["synthetic"]), set(BASELINES))

    def test_no_unrun_or_failed_competitor_can_be_ignored(self):
        for mutation in ("remove", "failed", "unversioned", "slow", "low_score"):
            rows = self.cases()
            competitor = rows[1]["results"]["megahit"]
            if mutation == "remove":
                del rows[1]["results"]["megahit"]
            elif mutation == "failed":
                competitor["status"] = "failed"
            elif mutation == "unversioned":
                competitor["sha256"] = ""
            elif mutation == "slow":
                rows[1]["results"]["ivanka"]["seconds"] = 3
            elif mutation == "low_score":
                rows[1]["results"]["ivanka"]["score"] = 80
            with self.subTest(mutation=mutation):
                self.assertFalse(self.qualified(rows)["pass"])

    def test_raw_contigs_cannot_certify_pipeline_dominant_recovery(self):
        rows = self.cases()
        for tool in ASSEMBLERS:
            rows[1]["results"][tool]["score_origin"] = "assembler_fasta_diagnostic_v1"
        result = self.qualified(rows)
        self.assertFalse(result["pass"])
        self.assertIn("clonal-1:not_final_MiCall_output_or_timing",
                      result["errors"])

    def test_micall_pipeline_timing_is_required_on_both_cohorts(self):
        rows = self.cases()
        rows[0]["results"]["ivanka"]["timing_origin"] = "standalone_wall"
        result = self.qualified(rows)
        self.assertFalse(result["pass"])
        self.assertIn("real-1:not_final_MiCall_output_or_timing",
                      result["errors"])

    def test_hxb2_truth_requires_independent_validator_attestation(self):
        for mutation in ("missing", "invalid", "wrong_schema", "digest"):
            rows = self.cases()
            proof = rows[1]["truth_validation"]
            if mutation == "missing":
                del rows[1]["truth_validation"]
            elif mutation == "invalid":
                proof["valid"] = False
            elif mutation == "wrong_schema":
                proof["schema"] = "generic_random_acgt_v1"
            else:
                proof["verification_sha256"] = "bad"
            with self.subTest(mutation=mutation):
                result = self.qualified(rows)
                self.assertFalse(result["pass"])
                self.assertIn("clonal-1:missing_verified_HXB2_truth",
                              result["errors"])

    def test_honest_empty_ivanka_contigs_do_not_imply_pipeline_failure(self):
        rows = self.cases()
        rows[1]["results"]["ivanka"]["contig_count"] = 0
        # The final MiCall dominant score remains valid; component
        # contig count is not an independent biological acceptance gate.
        self.assertTrue(self.qualified(rows)["pass"])

    def test_missing_real_or_synthetic_family_is_never_a_pass(self):
        self.assertFalse(self.qualified(self.cases()[:1])["pass"])
        self.assertFalse(self.qualified(self.cases()[1:])["pass"])

    def test_tool_binary_drift_is_rejected_within_cohort(self):
        rows = [self.sample("r-1", "real"), self.sample("r-2", "real"),
                self.sample("clonal-1", "synthetic", "clonal")]
        rows[1]["results"]["haploflow"]["sha256"] = "f"*64
        result = summarize_gate(rows, real_count=2,
                                synthetic_seeds=1, families=("clonal",))
        self.assertFalse(result["pass"])
        self.assertIn("real:haploflow:executable_changed_across_samples",
                      result["errors"])

    def test_all_exponents_gate_rejects_large_outlier(self):
        rows = [self.sample(f"r-{i}", "real") for i in range(3)]
        rows += [self.sample("s-1", "synthetic", "clonal")]
        rows[-2]["results"]["ivanka"]["seconds"] = 1200
        result = summarize_gate(rows, real_count=3,
                                synthetic_seeds=1, families=("clonal",))
        self.assertFalse(result["pass"])
        self.assertFalse(result["comparisons"]["real"]["megahit"]["pass"])


class ExpandedPhysicalMatrixTests(unittest.TestCase):
    def test_read_only_real_matrix_includes_weak_clean_competitors(self):
        from expanded.real_matrix import join_real_runs
        from unittest.mock import patch
        from expanded import real_matrix
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            specifications = {}
            cases = ["source-A", "source-B"]
            for number, tool in enumerate(x for x in ASSEMBLERS if x != "iva"):
                candidate_image = f"{number+1:064x}"
                path = root / f"{tool}.jsonl"
                records = []
                for name in cases:
                    weak = tool == "megahit"
                    source = {"fastq_sha256": ["a"*64, "b"*64]}
                    record = {
                        "sample": name, "invocation": tool + "-fresh",
                        "status": "finished", "failed": weak,
                        "provenance": source,
                        "iva": {"image_id": "f"*64, "exit_code": 0,
                                "seconds": 80, "container_wall_seconds": 82,
                                "timing_origin": "micall_in_container_monotonic_v1"},
                        "ivanka": {"image_id": candidate_image, "exit_code": 0,
                                   "seconds": 40, "container_wall_seconds": 42,
                                   "timing_origin": "micall_in_container_monotonic_v1"},
                        "best_contig_acceptance": {
                            "pass": not weak, "iva_score": 100,
                            "ivanka_score": 50 if weak else 120,
                            "method": "best_final_max_contig_local_alignment_over_reference_panel",
                            "reference_panel_sha256": real_matrix.PANEL,
                            "reference_count": 33,
                        },
                    }
                    records.append(record)
                path.write_text("".join(json.dumps(r)+"\n" for r in records))
                specifications[tool] = {
                    "image_id": candidate_image, "results_jsonl": str(path),
                }
            with patch.object(real_matrix, "EXPECTED", 2):
                matrix = join_real_runs(specifications)
            self.assertEqual(len(matrix), 2)
            self.assertEqual(matrix[0]["results"]["megahit"]["score"], 50)
            self.assertEqual(matrix[0]["results"]["megahit"]["status"], "success")
            self.assertEqual(matrix[0]["results"]["iva"]["score"], 100)

    def test_original_micall_sample_and_image_drift_fails(self):
        from expanded.real_matrix import join_real_runs
        with self.assertRaises(ValueError):
            join_real_runs({"ivanka": {"image_id": "a"*64, "results_jsonl": "/absent"}})

    def test_runner_uses_exactly_seven_image_names(self):
        from expanded.run_real import verify_images
        with self.assertRaises(ValueError):
            verify_images({"iva": "a"*64})

    def test_real_gate_only_accepts_rust_direct_ivanka_image(self):
        from expanded import run_real
        from unittest.mock import patch
        images = {tool: f"{i+1:064x}" for i, tool in enumerate(ASSEMBLERS)}
        images["iva"] = run_real.IVA_BASE
        image_info = {name: {
            "org.ottojung.expanded.assembler": name,
        } for name in ASSEMBLERS if name != "iva"}
        image_info["ivanka"] = {
            "org.ottojung.ivanka.execution": "rust-direct-default-read-backed-tile512",
        }
        def inspect(image, template):
            if template == "{{.Id}}":
                return image
            if template == "{{json .RootFS.Layers}}":
                return json.dumps(["same-base-layer"])
            name = next(name for name, value in images.items() if value == image)
            return json.dumps(image_info.get(name, {}))
        with patch.object(run_real, "inspect", side_effect=inspect):
            run_real.verify_images(images)
            image_info["ivanka"]["org.ottojung.ivanka.execution"] = (
                "native-fastq-read-backed-selector-trim-island-tile512"
            )
            with self.assertRaisesRegex(ValueError, "direct Rust"):
                run_real.verify_images(images)



class ExpandedExecutionTests(unittest.TestCase):
    def test_actual_fake_cli_executable_and_output_checks(self):
        import sys
        from expanded.adapters import execute
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            left, right = root / "R1.fastq", root / "R2.fastq"
            left.write_text("@x/1\nACGT\n+\nIIII\n")
            right.write_text("@x/2\nACGT\n+\nIIII\n")
            binary = root / "fake-ivanka"
            binary.write_text(
                f"#!{sys.executable}\n"
                "import sys\nfrom pathlib import Path\n"
                "out=sys.argv[sys.argv.index('--output')+1]\n"
                "Path(out).write_text('>c\\nACGT\\n')\n")
            binary.chmod(0o755)
            bins = require_programs(names=("ivanka",), paths={"ivanka": str(binary)})
            observed = execute("ivanka", left, right, root / "success",
                               bins, timeout=5)
            self.assertEqual(observed["status"], "success", observed)
            self.assertEqual(observed["output_sha256"],
                             binary_hash(root / "success/contigs.fasta"))
            binary.write_text(f"#!{sys.executable}\n")
            bins = require_programs(names=("ivanka",), paths={"ivanka": str(binary)})
            missing = execute("ivanka", left, right, root / "no-output",
                              bins, timeout=5)
            self.assertEqual(missing["status"], "failed")
            self.assertIn("no FASTA", missing["error"])


class ExpandedChildEnvironmentTests(unittest.TestCase):
    def test_ivanka_is_empty_and_external_tools_get_path_only(self):
        from expanded import adapters
        from unittest.mock import patch
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("ivanka", "abyss"):
                with self.subTest(assembler=name):
                    binaries = {name: {program: {"path": "/bin/true"}
                                       for program in PROGRAMS[name]}}
                    fake = SimpleNamespace(returncode=8, stdout="", stderr="test")
                    with patch.object(adapters.subprocess, "run", return_value=fake) as run:
                        result = adapters.execute(
                            name, root/"R1.fq", root/"R2.fq",
                            root/name, binaries, timeout=4,
                        )
                    self.assertEqual(result["status"], "failed")
                    expected = {} if name == "ivanka" else {
                        "PATH": "/usr/local/bin:/usr/bin:/bin",
                    }
                    self.assertEqual(run.call_args.kwargs["env"], expected)


@unittest.skipUnless(importlib.util.find_spec("Bio"),
                     "Biopython required for independent truth scoring")
class ExpandedTruthScoringTests(unittest.TestCase):
    def test_valid_iupac_ambiguities_are_scored_not_rejected(self):
        from expanded.score import read_fasta, reverse_complement
        with tempfile.TemporaryDirectory() as root:
            fasta = Path(root) / "ambiguity.fa"
            fasta.write_text(">ambiguous\nACGTRYSWKMBDHVN\n")
            self.assertEqual(read_fasta(fasta)[0], "ACGTRYSWKMBDHVN")
            for code in "ACGTRYSWKMBDHVN":
                self.assertEqual(reverse_complement(reverse_complement(code)),
                                 code)
            fasta.write_text(">invalid\nACGTZ\n")
            with self.assertRaises(ValueError):
                read_fasta(fasta)

    def test_ambiguous_contig_is_valid_but_not_exact(self):
        from expanded.score import dominant_truth_score, read_fasta
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            meta = generate_case(root, "clonal", 3, pairs=50)
            case = root / "clonal-s003"
            truth = case / meta["hidden_truth_file"]
            bases = list(read_fasta(truth)[0])
            bases[100] = "W"
            contig = root / "ambiguity.fa"
            contig.write_text(">ambiguous\n" + "".join(bases) + "\n")
            result = dominant_truth_score(meta, truth, contig)
            self.assertLess(result["score"], 1.0)
            self.assertGreater(result["score"], 0.9)
            self.assertFalse(result["dominant_exact"])

    def test_truth_scoring_is_separate_and_penalizes_errors(self):
        from expanded.score import dominant_truth_score, read_fasta
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            meta = generate_case(root, "clonal", 0, pairs=50)
            case = root / "clonal-s000"
            truth = case / meta["hidden_truth_file"]
            reference = read_fasta(truth)[0]
            perfect = root / "perfect.fa"
            incorrect = root / "incorrect.fa"
            empty = root / "empty.fa"
            perfect.write_text(">perfect\n" + reference + "\n")
            wrong = list(reference)
            for i in range(90, 180):
                wrong[i] = "G" if wrong[i] != "G" else "C"
            incorrect.write_text(">incorrect\n" + "".join(wrong) + "\n")
            empty.write_text("")
            perfect_result = dominant_truth_score(meta, truth, perfect)
            damaged = dominant_truth_score(meta, truth, incorrect)
            nothing = dominant_truth_score(meta, truth, empty)
            self.assertEqual(perfect_result["score"], 1)
            self.assertTrue(perfect_result["dominant_exact"])
            from expanded.score import reverse_complement
            reverse = root / "reverse.fa"
            reverse.write_text(">reverse\n" + reverse_complement(reference) + "\n")
            reversed_result = dominant_truth_score(meta, truth, reverse)
            self.assertEqual(reversed_result["score"], perfect_result["score"])
            self.assertTrue(reversed_result["dominant_exact"])
            self.assertLess(damaged["score"], 1)
            self.assertEqual(nothing["score"], 0)
            self.assertFalse(nothing["dominant_exact"])


class ExpandedRetrospectiveTests(unittest.TestCase):
    def test_project_breakdown_and_outlier_descriptions(self):
        from expanded.analyze_results import analyze
        records = []
        for index, (iva, ivanka, score_a, score_b) in enumerate([
                (50, 20, 100, 120), (25, 42, 100, 96)]):
            records.append({
                "sample": f"private-sample-{index}",
                "status": "finished",
                "provenance": {"micall_project_code": "HCV"},
                "iva": {"exit_code": 0, "seconds": iva},
                "ivanka": {"exit_code": 0, "seconds": ivanka},
                "best_contig_acceptance": {
                    "iva_score": score_a, "ivanka_score": score_b,
                    "iva_contig_count": 15, "ivanka_contig_count": 2,
                    "iva_best_contig_length": 950,
                    "ivanka_best_contig_length": 990,
                },
            })
        result = analyze(records, expected=2)
        self.assertTrue(result["complete"])
        self.assertEqual(result["runtime"], {"wins": 1, "losses": 1, "ties": 0})
        self.assertEqual(result["alignment"], {"wins": 1, "losses": 1, "ties": 0})
        self.assertEqual(result["project_groups"]["HCV"]["n"], 2)
        self.assertEqual(result["runtime_wins_with_alignment_loss"], 0)
        self.assertNotIn("private-sample-0",
                         json.dumps(result))
        self.assertFalse(analyze(records[:1], expected=2)["complete"])


class ExpandedToolProfileTests(unittest.TestCase):
    def test_profiles_are_fixed_not_tuned_from_sample_truth(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            r1, r2 = root / "r1.fq.gz", root / "r2.fq.gz"
            r1.write_bytes(b"")
            r2.write_bytes(b"")
            tools = {"haploflow", "abyss", "spades"}
            for name in tools:
                binaries = {name: {binary: {"path": f"/usr/bin/{binary}"}
                                   for binary in PROGRAMS[name]}}
                work = root / name
                work.mkdir()
                cmd, _ = steps(name, r1, r2, work, binaries)
                words = cmd[0]
                if name == "haploflow":
                    self.assertEqual(words[words.index("--strict")+1], "0")
                elif name == "abyss":
                    self.assertIn("B=128M", words)
                    self.assertIn("j=2", words)
                else:
                    self.assertEqual(words[words.index("--phred-offset")+1], "33")



if __name__ == "__main__":
    unittest.main()

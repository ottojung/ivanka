#!/usr/bin/env python3
"""Compare IVA and Riva by running MiCall's actual de novo sample pipeline twice.

No local implementation of mapping, stitching, sam2aln, or aln2counts.
Only the assembler boundary is swapped via micall.drivers.sample.denovo.
Private FASTQs/outputs never belong in the repository.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("RIVA_DATA", "/workspace/denovo-example-io-1"))
MICALL = Path(os.environ.get("MICALL_REPO", "/workspace/qai-repo/repos/MiCall"))
RESULTS = Path(os.environ.get("RIVA_FULL_RESULTS", "/workspace/riva-full-micall-results"))
HXB2 = DATA / "hxb2.fasta"
SOURCE_FILES = ("conseq.csv", "conseq_all.csv", "genome_coverage.csv",
                "genome_concordance.csv", "coverage_summary.csv", "concordance.csv",
                "remap_counts.csv", "contigs.csv", "stitched_contigs.csv",
                "unstitched_contigs.csv", "unstitched_conseq.csv",
                "unstitched_genome_coverage.csv", "unstitched_remap_counts.csv")
MIN_CONTIG_LENGTH = 600

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()

def git_commit(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"],
                                   text=True).strip()

def metadata() -> dict:
    return {
        "micall_commit": git_commit(MICALL),
        "riva_commit": git_commit(ROOT),
        "hxb2_sha256": sha256(HXB2),
        "input_manifest_sha256": sha256(DATA / "manifest.tsv"),
        "minimum_assembler_contig_length": MIN_CONTIG_LENGTH,
        "pipeline": "MiCall Sample.process preassembly once, then same MiCall run_denovo and process_post_assembly for both arms",
    }

def manifest() -> list[dict]:
    with (DATA / "manifest.tsv").open(newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))

def input_pair(row: dict) -> tuple[Path, Path]:
    folder = DATA / "samples" / row["sample"]
    paths = tuple(folder / f"{row['sample']}_L001_R{i}_001.fastq.gz" for i in (1, 2))
    if not all(p.is_file() for p in paths):
        raise FileNotFoundError(f"Missing input FASTQs: {row['sample']}")
    return paths

def cached_iva(row: dict, output: Path) -> None:
    source = DATA / "samples" / row["sample"] / f"unstitched_contigs_{row['kive_run_id']}.csv"
    with source.open(newline="") as f, output.open("w") as dest:
        reader = csv.DictReader(f)
        if "contig" not in (reader.fieldnames or []):
            raise ValueError(f"No contig column in {source}")
        for i, item in enumerate(reader, 1):
            seq = item["contig"].strip().upper()
            if seq:
                dest.write(f">iva_kive_{i}\n{seq}\n")

def filter_assembler_contigs(path: Path, min_length: int) -> int:
    # This is the same assembly-boundary filter for both arms, before MiCall
    # appends its G2P-derived contigs and performs read-supported stitching.
    from Bio import SeqIO
    temporary = path.with_suffix(".filtered.fasta")
    with path.open() as f, temporary.open("w") as dest:
        count = 0
        for record in SeqIO.parse(f, "fasta"):
            if len(record.seq) >= min_length:
                SeqIO.write(record, dest, "fasta")
                count += 1
    temporary.replace(path)
    return count

def adapter_for(row: dict, arm: str, iva_mode: str, riva: Path,
                original_denovo, stats: dict):
    def run(fastq1: Path, fastq2: Path, fasta: Path,
            merged_contigs_csv: Path | None = None):
        # Arguments are MiCall's own *trimmed* FASTQs, not the raw data.
        started = time.monotonic()
        fasta = Path(fasta)
        if arm == "iva":
            if iva_mode == "run":
                # Run the genuine IVA invocation, including MiCall's own
                # G2P seed-contig handling and merged-mates setup.
                original_denovo(fastq1, fastq2, fasta, merged_contigs_csv)
            else:
                # Historical IVA contigs from the Kive run, provided in the
                # private dataset. Clearly label this REPLAY, not an IVA run.
                cached_iva(row, fasta)
        else:
            proc = subprocess.run([
                str(riva), "--reads1", str(fastq1), "--reads2", str(fastq2),
                "--output", str(fasta),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stats["riva_stderr_tail"] = proc.stderr[-2000:]
            if proc.returncode:
                raise RuntimeError(f"Riva exit {proc.returncode}: {proc.stderr[-350:]}")
            # Riva currently ignores G2P seeds internally; MiCall still
            # incorporates the *same* merged seed contigs downstream.
        stats["assembler_seconds"] = round(time.monotonic() - started, 2)
        stats["assembled_contigs_passing_filter"] = filter_assembler_contigs(
            fasta, MIN_CONTIG_LENGTH)
    return run

def csv_metadata(path: Path) -> dict:
    if not path.is_file():
        return {"exists": False}
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        count = sum(1 for _ in reader)
        columns = reader.fieldnames or []
    return {"exists": True, "rows": count, "sha256": sha256(path),
            "columns": columns}

def pipeline_metrics(folder: Path, reference: str) -> dict:
    from Bio.Align import PairwiseAligner
    final_conseq = folder / "conseq.csv"
    aligner = PairwiseAligner()
    aligner.mode = "global"
    aligner.end_gap_score = -1
    scores: list[float] = []
    seq_lengths: list[int] = []
    if final_conseq.exists():
        with final_conseq.open(newline="") as f:
            for row in csv.DictReader(f):
                if row.get("consensus-percent-cutoff") != "MAX":
                    continue
                seq = row.get("sequence", "").upper()
                if seq and set(seq) <= set("ACGTN-"):
                    scores.append(float(aligner.score(reference, seq)))
                    seq_lengths.append(len(seq))
    coverage_values = []
    coverage_file = folder / "genome_coverage.csv"
    if coverage_file.is_file():
        with coverage_file.open(newline="") as f:
            for record in csv.DictReader(f):
                value = record.get("coverage")
                if value not in (None, ""):
                    try:
                        coverage_values.append(float(value))
                    except ValueError:
                        pass
    return {
        "genome_coverage_total_rows_with_depth": len(coverage_values),
        "genome_coverage_nonzero_rows": sum(c > 0 for c in coverage_values),
        "genome_coverage_mean_depth": (sum(coverage_values)/len(coverage_values)
                                       if coverage_values else None),
        "best_hxb2_final_conseq_score": max(scores, default=None),
        "final_conseq_max_lengths": sorted(seq_lengths, reverse=True),
        "final_conseq_max_count": len(scores),
        "files": {name: csv_metadata(folder / name) for name in SOURCE_FILES},
    }

def execute_arm(row: dict, arm: str, output_dir: Path,
                pssm, riva: Path, iva_mode: str, reference: str) -> dict:
    # Delayed imports keep --probe usable even when native MiCall deps are
    # unavailable. Do not substitute a mock processing pipeline.
    import micall.drivers.sample as sample_module
    from micall.drivers.sample import Sample
    from micall.core.denovo import denovo as iva_denovo

    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "sample_info.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["project"])
        w.writeheader()
        w.writerow({"project": row["project"]})
    # The private dataset contains original inputs but no per-run bad-cycle file.
    # Match the existing alpha benchmark's explicitly empty bad-cycle policy.
    (output_dir / "bad_cycles.csv").write_text("tile,cycle\n")

    fq1, fq2 = input_pair(row)
    sample = Sample(
        fastq1=str(fq1), fastq2=str(fq2),
        sample_info_csv=str(output_dir / "sample_info.csv"),
        scratch_path=str(output_dir),
    )
    details: dict = {"arm": arm, "iva_mode": iva_mode if arm == "iva" else None}
    started = time.monotonic()
    adapter = adapter_for(row, arm, iva_mode, riva, iva_denovo, details)
    with patch.object(sample_module, "denovo", adapter):
        if arm == "iva":
            # Run ALL normal MiCall stages once; no reimplementation.
            sample.process(pssm=pssm, use_denovo=True)
        else:
            # The upstream MiCall run is independent of the assembler.
            # Reuse the exact trimmed pairs and G2P outputs from the IVA arm,
            # then invoke MiCall's original run_denovo + post-assembly code.
            # This saves substantial deterministic work and guarantees
            # byte-for-byte identical input to the two assembler boundaries.
            source = RESULTS / row["sample"] / "iva"
            shared = ("trimmed1.fastq", "trimmed2.fastq",
                      "merged_contigs.csv", "g2p_aligned.csv",
                      "g2p_summary.csv", "g2p.csv",
                      "read_entropy.csv", "merge_lengths.csv")
            for name in shared:
                src = source / name
                if not src.is_file():
                    raise FileNotFoundError(f"IVA MiCall preprocessing missing: {src}")
                dest = output_dir / name
                dest.unlink(missing_ok=True)
                os.link(src, dest)
            excluded_seeds = sample_module.exclude_extra_seeds((), row["project"])
            sample.run_denovo(excluded_seeds)
            sample.process_post_assembly(
                prefix="", use_denovo=True, excluded_projects=())
            sample.process_post_assembly(
                prefix="unstitched_", use_denovo=True, excluded_projects=())
            details["upstream_preprocessing"] = "byte-identical MiCall outputs reused from IVA arm"
    details["pipeline_seconds"] = round(time.monotonic() - started, 2)
    details["metrics"] = pipeline_metrics(output_dir, reference)
    return details

def compare_outputs(iva: dict, riva: dict) -> dict:
    before = iva["metrics"]
    after = riva["metrics"]
    report = {}
    for name in SOURCE_FILES:
        a = before["files"][name]
        b = after["files"][name]
        report[name] = {
            "iva_rows": a.get("rows"),
            "riva_rows": b.get("rows"),
            "same_bytes": (a.get("sha256") == b.get("sha256")
                           if a.get("sha256") and b.get("sha256") else None),
        }
    return {
        "files": report,
        "iva_coverage_nonzero_rows": before["genome_coverage_nonzero_rows"],
        "riva_coverage_nonzero_rows": after["genome_coverage_nonzero_rows"],
        "iva_coverage_mean_depth": before["genome_coverage_mean_depth"],
        "riva_coverage_mean_depth": after["genome_coverage_mean_depth"],
        "iva_final_MAX_conseqs": before["final_conseq_max_count"],
        "riva_final_MAX_conseqs": after["final_conseq_max_count"],
    }


def acceptance(iva: dict, riva: dict) -> dict:
    baseline = iva["metrics"]["best_hxb2_final_conseq_score"]
    score = riva["metrics"]["best_hxb2_final_conseq_score"]
    if baseline is None or score is None:
        return {"pass": False, "reason": "No scored MAX consensus"}
    passed = score >= (0.95 * baseline if baseline > 0 else baseline)
    return {"pass": passed, "iva_score": baseline, "riva_score": score,
            "threshold": 0.95 * baseline if baseline > 0 else baseline}

def probe(args) -> int:
    print("MiCall source:", MICALL, "exists:", MICALL.is_dir())
    print("MiCall commit:", git_commit(MICALL))
    print("Data samples:", len(manifest()))
    print("HXB2:", HXB2.is_file())
    print("Riva binary:", Path(args.riva), "exists:", Path(args.riva).exists())
    for exe in ("iva", "merge-mates", "bowtie2", "samtools", "cutadapt",
                "minimap2", "blastn"):
        print("executable", exe, shutil.which(exe))
    sys.path.insert(0, str(MICALL))
    try:
        from micall.drivers.sample import Sample
        from micall.g2p.pssm_lib import Pssm
        print("MiCall Sample + Pssm import: OK", Sample.__name__, Pssm.__name__)
    except ImportError as exc:
        print("MiCall import dependency missing:", exc)
        return 2
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("both", "iva", "riva"), default="both")
    parser.add_argument("--iva-mode", choices=("run", "cached"), default="run")
    parser.add_argument("--riva", default=str(ROOT / "target/release/riva"))
    parser.add_argument("--sample", action="append", help="Subset sample ID (repeatable)")
    parser.add_argument("--probe", action="store_true", help="Check runtime without running")
    args = parser.parse_args()
    if args.probe:
        return probe(args)

    sys.path.insert(0, str(MICALL))
    from Bio import SeqIO
    from micall.g2p.pssm_lib import Pssm

    ref = str(next(SeqIO.parse(HXB2, "fasta")).seq).upper()
    rows = [r for r in manifest() if not args.sample or r["sample"] in args.sample]
    if not rows:
        raise SystemExit("No matching samples")
    if args.mode in ("both", "riva") and not Path(args.riva).is_file():
        raise FileNotFoundError(args.riva)

    RESULTS.mkdir(parents=True, exist_ok=True)
    report_path = RESULTS / "full-micall-results.jsonl"
    baselines_file = RESULTS / "iva-full-micall-baselines.json"
    baselines = (json.loads(baselines_file.read_text())
                 if baselines_file.exists() else {})
    per_sample_baselines = RESULTS / "iva-baselines"
    per_sample_baselines.mkdir(exist_ok=True)
    run_id = f"{int(time.time())}-{os.getpid()}"
    provenance = metadata() | {
        "invocation_id": run_id,
        "riva_binary_sha256": sha256(Path(args.riva))
        if args.mode in ("both", "riva") else None,
        "iva_provenance": ("newly executed IVA" if args.iva_mode == "run"
                           else "historic Kive IVA contigs replayed"),
    }
    (RESULTS / "provenance.json").write_text(json.dumps(provenance, indent=2))
    pssm = Pssm()
    failed = 0
    with report_path.open("a", buffering=1) as report:
        for row in rows:
            sample_id = row["sample"]
            print(f"{sample_id}: running full MiCall, mode={args.mode}", flush=True)
            sample_result = {"sample": sample_id, "invocation_id": run_id,
                             "pipeline": provenance["pipeline"],
                             "iva_provenance": provenance["iva_provenance"],
                             "status": "started"}
            report.write(json.dumps(sample_result) + "\n")
            try:
                for arm in ("iva", "riva"):
                    if args.mode not in ("both", arm):
                        continue
                    out = RESULTS / sample_id / arm
                    sample_result[arm] = execute_arm(row, arm, out, pssm,
                                                      Path(args.riva),
                                                      args.iva_mode, ref)
                if "iva" in sample_result:
                    baselines[sample_id] = {
                        "details": sample_result["iva"],
                        "provenance": {
                            "micall_commit": provenance["micall_commit"],
                            "hxb2_sha256": provenance["hxb2_sha256"],
                            "input_manifest_sha256": provenance["input_manifest_sha256"],
                            "minimum_assembler_contig_length": MIN_CONTIG_LENGTH,
                            "iva_provenance": provenance["iva_provenance"],
                            "kive_run_id": row["kive_run_id"],
                        },
                    }
                    # Single-sample baseline files are independently atomic,
                    # so parallel MiCall experiments cannot lose baselines to
                    # simultaneous writes of the aggregate index.
                    dest = per_sample_baselines / f"{sample_id}.json"
                    tmp = dest.with_suffix(f".{os.getpid()}.new")
                    tmp.write_text(json.dumps(baselines[sample_id], indent=2))
                    tmp.replace(dest)
                    if len(rows) == 1:
                        tmp = baselines_file.with_suffix(f".{os.getpid()}.new")
                        baselines[sample_id] = json.loads(dest.read_text())
                        tmp.write_text(json.dumps(baselines, indent=2))
                        tmp.replace(baselines_file)
                if "riva" in sample_result:
                    saved = baselines.get(sample_id)
                    per_sample = per_sample_baselines / f"{sample_id}.json"
                    if per_sample.is_file():
                        saved = json.loads(per_sample.read_text())
                    if saved is None:
                        raise ValueError("IVA full-MiCall baseline missing: run --mode iva first")
                    expected = saved["provenance"]
                    for key in ("micall_commit", "hxb2_sha256",
                                "input_manifest_sha256",
                                "minimum_assembler_contig_length"):
                        if expected[key] != provenance[key]:
                            raise ValueError(f"IVA baseline provenance mismatch: {key}")
                    if expected["kive_run_id"] != row["kive_run_id"]:
                        raise ValueError("IVA baseline Kive run mismatch")
                    sample_result["acceptance"] = acceptance(
                        saved["details"], sample_result["riva"])
                    sample_result["comparison"] = compare_outputs(
                        saved["details"], sample_result["riva"])
                    sample_result["baseline_provenance"] = expected
                    if not sample_result["acceptance"]["pass"]:
                        failed += 1
                sample_result["status"] = "evaluated"
            except Exception as exc:
                failed += 1
                sample_result["status"] = "error"
                sample_result["error"] = f"{type(exc).__name__}: {exc}"
            report.write(json.dumps(sample_result, sort_keys=True) + "\n")
            print(sample_id, sample_result["status"],
                  sample_result.get("acceptance", {}), flush=True)
    return 1 if failed else 0

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    raise SystemExit(main())

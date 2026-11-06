"""Run the REAL Rust Ivanka binary against known-phase synthetic FASTQs.

No mutation of real data, no MiCall/IVA, no clinical inference. The binary
only sees paired FASTQs; source-phase truth is used by the evaluator AFTER
the output FASTA has been written.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from snv_q15_fastq import iter_original_pairs
from source_q15_phase_bridges import direct_source_links, directly_observed_candidate
from synthetic_phase_fidelity import analyze, fasta_records
from synthetic_phase_pairs import generate


def test_binary(binary, seed, *, variant_sites=(280,480), max_contigs=16,
                max_pairs=2000, timeout=90):
    path=Path(binary).resolve()
    if (not path.is_file() or type(seed) is not int
            or type(max_contigs) is not int or not 1<=max_contigs<=1000
            or type(max_pairs) is not int or not 2<=max_pairs<=100000
            or max_pairs%2 or type(timeout) is not int or not 1<=timeout<=1800):
        raise ValueError("Bounded genuine assembler smoke parameters required")
    with tempfile.TemporaryDirectory(prefix="ivanka-phase-smoke-") as folder:
        root=Path(folder)
        source=root/"synthetic-only"
        truth=generate(source,variants=variant_sites,seed=seed,
                       pairs_per_haplotype=max_pairs//2,error_rate=0)
        original1=source/"synthetic_R1.fastq.gz"
        original2=source/"synthetic_R2.fastq.gz"
        output=root/"rust-assembler-output.fasta"
        command=[str(path),"--reads1",str(original1),"--reads2",str(original2),
                 "--output",str(output),"--max-contigs",str(max_contigs),
                 "--max-pairs",str(max_pairs)]
        began=time.monotonic()
        proc=subprocess.run(command,stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,text=True,timeout=timeout)
        elapsed=time.monotonic()-began
        if proc.returncode:
            raise RuntimeError("Genuine Rust Ivanka failed with code "
                               +str(proc.returncode)+": "+proc.stderr[-400:])
        if not output.is_file():
            raise RuntimeError("Genuine Rust Ivanka produced no FASTA")
        records=fasta_records(output)
        if len(records)>max_contigs:
            raise RuntimeError("Assembler exceeded requested contig cap")
        truth_result=analyze(truth,records)
        source_links=direct_source_links(
            truth["phase_coupled_haplotypes"][0],variant_sites,
            iter_original_pairs(original1,original2,max_pairs=max_pairs))
        observed=[]
        for item in truth_result["contigs"]:
            alleles=item["allele_calls"]
            local=(directly_observed_candidate(alleles,source_links)
                   if all(base is not None for base in alleles) else None)
            observed.append({"length":item["length"],
                             "classification_known_truth":item["classification"],
                             "local_original_q15_link":
                                 local["status"] if local else "unknown"})
        return {
            "schema":"ivanka.synthetic_genuine_rust_phase_smoke.v1",
            "synthetic_only":True,
            "actual_rust_binary_sha256":
                hashlib.sha256(path.read_bytes()).hexdigest(),
            "seed":seed,
            "variant_positions_zero_based":list(variant_sites),
            "original_source_read_pairs":max_pairs,
            "original_q15_direct_linked_pairs":
                source_links["original_pairs_with_both_loci_observed"],
            "original_base_coverage_bridge_pairs":
                truth["read_pairs_directly_observing_both_variants"],
            "original_full_context_geometry_bridge_pairs":
                truth["read_pairs_covering_both_complete_31mer_contexts_before_errors"],
            "contigs":observed,
            "elapsed_seconds_host":round(elapsed,4),
            "unsupported_recombinant_count":
                truth_result["unsupported_recombinant_count"],
            "no_clinical_molecule_or_phase_claim":True,
            "no_original_or_real_FASTQ_modified":True,
        }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary",type=Path,required=True)
    parser.add_argument("--seeds",type=int,nargs="+",default=[19,39])
    parser.add_argument("--max-contigs",type=int,default=16)
    parser.add_argument("--max-pairs",type=int,default=2000)
    parser.add_argument("--timeout",type=int,default=90)
    parser.add_argument("--fail-on-recombinant",action="store_true")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if len(set(args.seeds))!=len(args.seeds):
        parser.error("Duplicate seed identifiers not accepted")
    reports=[test_binary(args.binary,seed,max_contigs=args.max_contigs,
                         max_pairs=args.max_pairs,timeout=args.timeout)
             for seed in args.seeds]
    report={"schema":"ivanka.synthetic_genuine_rust_phase_smoke_suite.v1",
            "results":reports,
            "known_truth_recombinants_found":
                sum(r["unsupported_recombinant_count"]for r in reports),
            "real_data_used":False,
            "automatic_production_release_permitted":False}
    if args.output is not None:
        target=args.output.resolve()
        target.parent.mkdir(parents=True,exist_ok=True)
        try:
            fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError:
            parser.error("Refusing to overwrite existing synthetic report")
        with os.fdopen(fd,'w') as stream:
            stream.write(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps(report,sort_keys=True,indent=2))
    if args.fail_on_recombinant and report["known_truth_recombinants_found"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()

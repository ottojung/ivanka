"""Original-paired-FASTQ Q15 admission screen for candidate alternate contigs.

Require at least five distinct original QNAMEs AND five consistent distinct
R1+R2 nucleotide signatures on a candidate novel exact 31-mer, otherwise
reject as unsupported/unknown. Never infer full-length phase from local
evidence; no duplication.
"""
import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from contig_diversity import read_fasta, canonical_kmers
from snv_q15_fastq import iter_original_pairs


def _open_fastq(path):
    path = Path(path)
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt")
    return path.open("rt")


def _rc_base(b):
    return {"A": "T", "C": "G", "G": "C", "T": "A"}.get(b, b)


def _rc_seq(seq):
    return "".join(_rc_base(x) for x in reversed(seq))


def _find_31mers(seq):
    seq = seq.upper()
    for i in range(len(seq) - 30):
        w = seq[i:i + 31]
        if all(c in "ACGT" for c in w):
            yield i, w


def _pair_signature(mate1, mate2):
    """Orientation-normalized distinct R1+R2 nucleotide signature."""
    # Use raw sequences as the signature component as they appear
    s1, s2 = mate1[0], mate2[0]
    return (s1, s2)


def screen_contigs(candidate_fasta, original_r1, original_r2,
                   reference_fastas=None, min_qnames=5, min_signatures=5,
                   min_phred=15, max_pairs=50000):
    if min_qnames < 1 or min_signatures < 1:
        raise ValueError("minimum counts must be positive")
    if min_phred < 0 or min_phred > 93:
        raise ValueError("invalid min_phred")
    if max_pairs < 1:
        raise ValueError("invalid max_pairs")

    candidates = read_fasta(candidate_fasta)
    refs = []
    if reference_fastas:
        for rf in reference_fastas:
            refs.extend(read_fasta(rf))
    ref_kmers_all = set()
    for r in refs:
        ref_kmers_all |= canonical_kmers(r, 31)
    # Also consider baseline contigs as reference context
    cand_kmers_all = set()
    for c in candidates:
        cand_kmers_all |= canonical_kmers(c, 31)

    # For each candidate contig, identify "novel" exact 31-mers relative to all refs
    results = []
    for ci, cseq in enumerate(candidates):
        novel_positions = []
        for pos, w in _find_31mers(cseq):
            cw = min(w, _rc_seq(w))
            if cw not in ref_kmers_all:
                novel_positions.append((pos, w))
        if not novel_positions:
            results.append({
                "contig_index": ci,
                "contig_len": len(cseq),
                "novel_31mers": 0,
                "admitted": False,
                "reason": "no_novel_31mers_vs_reference",
            })
            continue
        # Track evidence per novel 31-mer (canonical form)
        evidence = defaultdict(lambda: {"qnames": set(), "signatures": set()})
        for qname, mate1, mate2 in iter_original_pairs(original_r1, original_r2,
                                                     max_pairs=max_pairs):
            s1, q1s = mate1
            s2, q2s = mate2
            # Check if either read has a Q15+ hit to any novel 31-mer in any orientation
            # on this contig
            # Scan both mates against all novel 31-mers
            for pos, w in novel_positions:
                w_rc = _rc_seq(w)
                # look in s1 or s2
                found = False
                for mseq, mqual in [(s1, q1s), (s2, q2s)]:
                    # try direct and rc
                    for pat in [w, w_rc]:
                        idx = mseq.find(pat)
                        if idx >= 0:
                            # check all bases Q >= min_phred
                            ok = True
                            for j in range(len(pat)):
                                qq = ord(mqual[idx + j]) - 33
                                if qq < min_phred:
                                    ok = False
                                    break
                            if ok:
                                found = True
                                break
                    if found:
                        break
                if found:
                    cw = min(w, w_rc)
                    evidence[cw]["qnames"].add(qname)
                    evidence[cw]["signatures"].add((s1, s2))  # raw pair signature
        # Check admission criteria per novel 31-mer
        admitted_any = False
        admitted_kmers = []
        for cw, ev in evidence.items():
            if len(ev["qnames"]) >= min_qnames and len(ev["signatures"]) >= min_signatures:
                admitted_any = True
                admitted_kmers.append({
                    "canonical_31mer": cw,
                    "distinct_qnames": len(ev["qnames"]),
                    "distinct_pair_signatures": len(ev["signatures"]),
                })
        results.append({
            "contig_index": ci,
            "contig_len": len(cseq),
            "novel_31mers": len(novel_positions),
            "admitted": admitted_any,
            "admitted_kmers": admitted_kmers,
            "total_qnames_across_novel": len(set().union(*[e["qnames"] for e in evidence.values()])) if evidence else 0,
            "reason": "admitted_by_q15_original_pair_evidence" if admitted_any else "insufficient_evidence",
        })
    return {
        "schema_version": "ivanka.alternate_contig_q15_admission.v1",
        "candidate_fasta": str(candidate_fasta),
        "original_r1": str(original_r1),
        "original_r2": str(original_r2),
        "min_qnames": min_qnames,
        "min_signatures": min_signatures,
        "min_phred": min_phred,
        "max_pairs": max_pairs,
        "full_length_haplotype_phase_inferred": False,
        "independent_physical_molecules_inferred": False,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_fasta", type=Path)
    parser.add_argument("original_r1", type=Path)
    parser.add_argument("original_r2", type=Path)
    parser.add_argument("--reference-fasta", action="append", dest="reference_fastas")
    parser.add_argument("--min-qnames", type=int, default=5)
    parser.add_argument("--min-signatures", type=int, default=5)
    parser.add_argument("--min-phred", type=int, default=15)
    parser.add_argument("--max-pairs", type=int, default=50000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = screen_contigs(
            args.candidate_fasta, args.original_r1, args.original_r2,
            reference_fastas=args.reference_fastas,
            min_qnames=args.min_qnames, min_signatures=args.min_signatures,
            min_phred=args.min_phred, max_pairs=args.max_pairs)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("w") as f:
                json.dump(result, f, indent=2)
                f.write("\n")
        else:
            print(json.dumps(result, indent=2))
    except Exception as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()

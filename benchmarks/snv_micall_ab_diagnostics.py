"""Read-only MiCall A/B: separate matched-locus depth and unpaired changes.

Never interpret alignment read counts as independent physical DNA molecules
or a passed phase-safety criterion. Compare only exact matching coordinates.
"""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()


def nuc_rows(folder):
    path=Path(folder)/"nuc.csv"
    if not path.is_file():raise FileNotFoundError(path)
    keyed=defaultdict(Counter)
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            if row.get("q-cutoff")!="15":continue
            key=tuple(row.get(k,"") for k in
                      ("seed","region","q-cutoff","query.nuc.pos",
                       "refseq.nuc.pos","genome.pos"))
            for base in ("A","C","G","T"):
                keyed[key][base]+=int(row[base] or 0)
            keyed[key]["coverage"]+=int(row.get("coverage") or 0)
    return dict(keyed)


def max_rows(folder):
    path=Path(folder)/"conseq.csv"
    if not path.is_file():raise FileNotFoundError(path)
    rows=Counter()
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            if row.get("q-cutoff")=="15" and row.get("consensus-percent-cutoff")=="MAX":
                rows[(row["region"],row["offset"],row["sequence"])]+=1
    return rows


def compare(base,candidate, *, threshold=100, allele_floor=10):
    base,candidate=Path(base),Path(candidate)
    if (type(threshold) is not int or threshold < 1
            or type(allele_floor) is not int or allele_floor < 1):
        raise ValueError("Positive integer thresholds required")
    b,c=nuc_rows(base),nuc_rows(candidate)
    if not b or not c:
        raise ValueError("Both original MiCall arms need Q15 nucleotide evidence")
    shared=set(b)&set(c); missing=set(b)-set(c); new=set(c)
    high={p for p in b if b[p]["coverage"]>=threshold}
    lost=sum(b[p]["coverage"]>=threshold and c[p]["coverage"]<threshold
             for p in shared)
    allele_loss=sum(b[p][allele]>=allele_floor and c[p][allele]<allele_floor
                    for p in shared for allele in ("A","C","G","T"))
    totals=lambda xs:sum(xs[p]["coverage"] for p in xs)
    cb,cc=max_rows(base),max_rows(candidate)
    return {
        "schema_version":"ivanka.snv_micall_original_read_ab_diagnostic.v1",
        "base_conseq_sha256":sha256(base/"conseq.csv"),
        "candidate_conseq_sha256":sha256(candidate/"conseq.csv"),
        "base_nuc_sha256":sha256(base/"nuc.csv"),
        "candidate_nuc_sha256":sha256(candidate/"nuc.csv"),
        "base_q15_max_sequences":sum(cb.values()),
        "candidate_q15_max_sequences":sum(cc.values()),
        "identical_q15_max_sequence_multiset":cb==cc,
        "baseline_max_sequence_rows_lost":sum((cb-cc).values()),
        "candidate_max_sequence_rows_added":sum((cc-cb).values()),
        "matched_q15_nuc_loci":len(shared),
        "baseline_only_q15_nuc_loci":len(missing),
        "candidate_only_q15_nuc_loci":len(new),
        "baseline_matched_nuc_depth_total":totals({k:b[k] for k in shared}),
        "candidate_matched_nuc_depth_total":totals({k:c[k] for k in shared}),
        "baseline_q15_loci_with_depth_at_least_100":len(high),
        "baseline_high_depth_loci_missing_candidate":len(high&missing),
        "matched_loci_dropped_below_depth_100":lost,
        "baseline_q15_allele_calls_ge_10_lost_on_matched_loci":allele_loss,
        "no_detected_matched_q15_allele_or_high_depth_loss":(
            allele_loss==0 and lost==0 and len(high&missing)==0),
        "threshold":threshold,
        "allele_floor":allele_floor,
        "full_length_haplotype_phase_authenticated":False,
        "independent_physical_molecule_count_authenticated":False,
        "original_remap_pair_assignment_equivalence_proven":False,
        "interpretation":"Missing/unmatched loci require manual seed/reference reconciliation; read depth is not DNA molecule count.",
    }


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("baseline",type=Path)
    p.add_argument("experiment",type=Path)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    report=compare(args.baseline,args.experiment)
    output=json.dumps(report,sort_keys=True,indent=2)+"\n"
    if args.output:
        dest=args.output.resolve()
        for folder in (args.baseline,args.experiment):
            root=folder.resolve()
            if dest==root or root in dest.parents:
                p.error("Refusing to modify original MiCall output")
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():p.error("Refusing to overwrite an earlier comparison")
        with dest.open("x") as f:f.write(output)
    else:print(output)


if __name__=="__main__":
    main()

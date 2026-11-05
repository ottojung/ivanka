"""Strict paired-remap A/B: detect assignment changes, not molecule identities."""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):h.update(block)
    return h.hexdigest()


def assignments(folder):
    root=Path(folder)
    refs=root/"scratch"/"remap_conseq.csv"
    sams=root/"scratch"/"remap.csv"
    if not refs.is_file() or not sams.is_file():
        raise FileNotFoundError("Original paired remap sources missing")
    ref={}
    with refs.open(newline="") as f:
        for row in csv.DictReader(f):
            key=row["region"]
            if not key or not row["sequence"] or key in ref:
                raise ValueError("Invalid or duplicate remap reference")
            ref[key]=hashlib.sha256(
                row["sequence"].upper().encode()).hexdigest()
    pairs=defaultdict(list)
    with sams.open(newline="") as f:
        for row in csv.DictReader(f):
            flag=int(row["flag"])
            proper=bool(flag&0x1 and flag&0x2) and not bool(
                flag&(0x4|0x8|0x100|0x800))
            if proper and row["rname"] not in ref:
                raise ValueError("Unrecognized original proper-pair remap sequence")
            if not row["qname"]:
                raise ValueError("Original remap pair without qname")
            pairs[row["qname"]].append((
                flag,ref.get(row["rname"]) if proper else None,proper))
    out={}
    excluded_improper=excluded_nonstrict=0
    for qname, observations in pairs.items():
        if any(not value[2] for value in observations):
            excluded_improper+=1
            continue
        flags=[v[0] for v in observations]
        if (len(flags)!=2 or
            sum(bool(f&0x40) for f in flags)!=1 or
            sum(bool(f&0x80) for f in flags)!=1 or
            flags[0]&0x40==flags[1]&0x40 or
            observations[0][1]!=observations[1][1]):
            excluded_nonstrict+=1
            continue
        out[qname]=observations[0][1]
    return out,{"remap_csv_sha256":sha(sams),
                "remap_conseq_csv_sha256":sha(refs),
                "strict_original_pair_qnames":len(out),
                "excluded_improper_or_unmapped_pair_qnames":excluded_improper,
                "excluded_nonstrict_or_multiassigned_pair_qnames":excluded_nonstrict,
                "original_qnames_in_remap":len(pairs),
                "reference_sequence_count":len(set(ref.values()))}


def compare(baseline,candidate):
    b,b_proof=assignments(baseline)
    c,c_proof=assignments(candidate)
    common=b.keys()&c.keys()
    changed=sum(b[q]!=c[q] for q in common)
    b_ct=Counter(b.values())
    c_ct=Counter(c.values())
    delta={k:b_ct[k]-c_ct[k] for k in b_ct}
    return {
        "schema_version":"ivanka.snv_micall_strict_original_pair_assignment_ab.v1",
        "baseline":b_proof,"experimental":c_proof,
        "original_qnames_mapped_by_both":len(common),
        "original_qnames_only_baseline":len(b.keys()-c.keys()),
        "original_qnames_only_experimental":len(c.keys()-b.keys()),
        "same_original_qname_placed_on_different_reference_sequence":changed,
        "baseline_reference_sequence_count":len(b_ct),
        "experimental_reference_sequence_count":len(c_ct),
        "new_reference_sequences_in_experimental":len(c_ct.keys()-b_ct.keys()),
        "baseline_reference_sequences_absent_in_experimental":len(b_ct.keys()-c_ct.keys()),
        "reference_sequences_with_at_least_10_fewer_assigned_pairs":
            sum(loss>=10 for loss in delta.values()),
        "largest_loss_of_original_qnames_for_one_reference_sequence":
            max(delta.values(),default=0),
        "exact_original_pair_placement_equivalence":b==c,
        "original_qnames_are_independent_DNA_molecules":False,
        "original_qname_mapped_to_multiple_contigs_in_single_strict_arm":False,
        "long_range_phase_validated":False,
        "interpretation":"Only fully proper primary strict pairs count; incomplete/improper/multimapped pairs are reported but excluded. Remap placements are not independent biological molecules.",
    }


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline",type=Path)
    parser.add_argument("experiment",type=Path)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    result=json.dumps(compare(args.baseline,args.experiment),sort_keys=True,indent=2)+"\n"
    if args.output is None:
        print(result)
    else:
        path=args.output.resolve()
        if path.exists():parser.error("Refusing to overwrite existing comparison")
        for src in (args.baseline,args.experiment):
            base=src.resolve()
            if path==base or base in path.parents:
                parser.error("Refusing to modify original MiCall source")
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("x") as stream:stream.write(result)


if __name__=="__main__":main()

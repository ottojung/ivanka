"""Read-only shared-node consensus proposals from genuine paired observations.

This does not edit MiCall outputs, infer distant phase, or turn a shared
read into multiple independent molecules. It proposes only exact ACGT
replacements for fully masked, uniquely flanked, conserved HCV blocks.
"""
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import re
from types import SimpleNamespace

from consensus_mask_stage_audit import exact_flank_correspondence, mask_runs
from shared_block_consensus_candidate import audit_remap
from shared_locus_remap_coverage import group_loci

_HCV = re.compile(r"^\d+-(HCV-\d+[a-z])$")
_BASES = frozenset("ACGT")
_SUFFIX = "|ivanka_hypothesis="


def proposals(final_rows, reference_rows, sam_rows, required_depth=100):
    """Return (hypothetical final rows, evidence), without altering inputs."""
    if required_depth < 1:
        raise ValueError("Positive per-position evidence depth required")
    refs = {}
    for row in reference_rows:
        name, seq = row["region"], row["sequence"].upper()
        if name in refs:
            raise ValueError("Duplicate remapping reference")
        refs[name] = seq
    observations = list(sam_rows)
    if any(_SUFFIX in r["qname"] for r in observations):
        raise ValueError("Only original remap reads, never synthetic projections")
    produced, evidence = [], []
    for row in final_rows:
        result = dict(row)
        seq = row["sequence"]
        match = _HCV.fullmatch(row.get("region", ""))
        if (match and row.get("q-cutoff") == "15"
                and row.get("consensus-percent-cutoff") == "MAX"):
            for start, end in mask_runs(seq):
                if seq[start:end] != "x" * (end - start):
                    continue
                compatible = {
                    name: reference for name, reference in refs.items()
                    if (match_ref := _HCV.fullmatch(name))
                    and match_ref.group(1) == match.group(1)
                    and set(reference) <= _BASES
                    and exact_flank_correspondence(seq, reference,
                                                    start, end, anchor=31)
                    is not None
                }
                if len(compatible) < 2:
                    continue
                masked = SimpleNamespace(sequence=seq, start=start, end=end)
                try:
                    group_loci(masked, compatible, anchor=31)
                except ValueError:
                    # Not a single, unambiguous allele shared by all refs.
                    continue
                support = audit_remap(masked, compatible, observations,
                                      required_depth=required_depth)
                allele = support["read_derived_candidate"]
                complete = support["complete_block_observations"][
                    "distinct_pair_sequence_evidence"]
                full_support = (complete or {}).get(
                    "shared_allele_distinct_pair_sequences", 0)
                if (not support["eligible"] or full_support < 1
                        or not allele or len(allele) != end-start
                        or set(allele) - _BASES):
                    continue
                result["sequence"] = (result["sequence"][:start] + allele
                                      + result["sequence"][end:])
                evidence.append({
                    "region": row["region"], "start": start, "end": end,
                    "length": end-start, "reference_names": sorted(compatible),
                    "minimum_distinct_pair_sequences_per_base": min(
                        item["shared_base_distinct_pair_sequences"]
                        for item in support["positions"]),
                    "complete_local_allele_distinct_pair_sequences": full_support,
                    "original_qnames_only": True,
                    "provenance": "observed_shared_local_sequence_not_haplotype_phase",
                })
        produced.append(result)
    return produced, evidence


def _hash(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("final_conseq_csv", type=Path)
    parser.add_argument("remap_conseq_csv", type=Path)
    parser.add_argument("original_remap_csv", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--required-depth", type=int, default=100)
    args = parser.parse_args()
    sources = (args.final_conseq_csv, args.remap_conseq_csv,
               args.original_remap_csv)
    targets = (args.output, args.report)
    if (len({p.resolve() for p in (*sources, *targets)}) != 5
            or any(p.exists() for p in targets)):
        parser.error("Output paths must be new, distinct files")
    with sources[0].open(newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        original = list(reader)
    with sources[1].open(newline="") as handle:
        reference_rows = list(csv.DictReader(handle))
    with sources[2].open(newline="") as handle:
        sam_rows = list(csv.DictReader(handle))
    updated, evidence = proposals(original, reference_rows, sam_rows,
                                  args.required_depth)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(updated)
    report = {
        "hypothetical_only": True,
        "independent_molecules_claimed": False,
        "haplotype_phase_proven": False,
        "per_position_depth": args.required_depth,
        "source_sha256": {str(p): _hash(p) for p in sources},
        "output_sha256": _hash(args.output),
        "proposals": evidence,
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"proposals": len(evidence),
                      "report": str(args.report)}, sort_keys=True))


if __name__ == "__main__":
    main()

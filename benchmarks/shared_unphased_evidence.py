"""Read-only original-pair-supported shared sequence, never inferred phase.

A shared-local block and nearby variant-marker alleles are evidence FEATURES,
not assigned haplotypes. Original read qnames are redacted unless explicitly
requested; identical paired-sequence signatures do not imply distinct
physical molecules. No MiCall consensus or SAM records are modified.
"""
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

from shared_block_consensus_candidate import (
    _pair_signature, _strict_pair, canonical_base,
)
from shared_block_phase_links import discover_markers
from shared_locus_remap_coverage import sam_observations


def _complete_calls(pair, coords, allele, markers, minimum_quality):
    """Require each local site to be directly observed without mate conflicts."""
    calls = defaultdict(set)
    ref = pair[0]["rname"]
    for row in pair:
        for site, base, _, expected in sam_observations(
                row, coords[ref], minimum_quality):
            canonical = (allele[site] if site < len(allele)
                         else markers[site-len(allele)]["alleles"][ref])
            try:
                calls[site].add(canonical_base(base, expected, canonical))
            except ValueError:
                # Ambiguous bases/strand disagreement are not valid witnesses.
                calls[site].add(None)
    block = ("".join(next(iter(calls[i])) for i in range(len(allele)))
             if all(len(calls[i]) == 1 and None not in calls[i]
                    for i in range(len(allele))) else None)
    markers_observed = [
        next(iter(calls[len(allele)+j]))
        if len(calls[len(allele)+j]) == 1
        and None not in calls[len(allele)+j] else None
        for j in range(len(markers))
    ]
    return block, markers_observed


def build_shared_evidence(masked, references, sam_rows, anchor=31,
                          radius=600, minimum_quality=15,
                          include_qnames=False, include_direct_links=False):
    """Audit only complete directly observed original-pair local alleles.

    Distinct sequence-signature support is counted for a feature ONLY if
    every strict original qname carrying that signature makes the same
    nonmissing observation. Contradictory/partial signatures are withheld.
    This conservative count is not an independent molecule count.
    """
    if (minimum_quality < 0 or not isinstance(include_qnames, bool)
            or not isinstance(include_direct_links, bool)):
        raise ValueError("Invalid quality or provenance disclosure option")
    allele, loci, markers = discover_markers(
        masked, references, anchor, radius)
    coords = {name: dict(sites) for name, sites in loci.items()}
    for j, marker in enumerate(markers):
        for ref, (pos, expected) in marker["coords"].items():
            coords[ref][pos] = (len(allele) + j, expected)
    groups = defaultdict(list)
    for row in sam_rows:
        groups[row["qname"]].append(row)

    # Group original qname observations by original paired SEQUENCE signature,
    # never by synthetic remap row multiplicity or per-target coverage.
    observations = {}
    pair_signatures = {}
    by_signature = defaultdict(lambda: defaultdict(set))
    raw_node_qnames = defaultdict(set)
    for qname, pair in groups.items():
        if not qname or not _strict_pair(pair) or pair[0]["rname"] not in coords:
            continue
        try:
            signature = _pair_signature(pair)
        except ValueError:
            continue
        block, observed_markers = _complete_calls(
            pair, coords, allele, markers, minimum_quality)
        features = {("block", 0): block}
        features.update({("marker", j): value
                         for j, value in enumerate(observed_markers)})
        observations[qname] = features
        pair_signatures[qname] = signature
        for key, value in features.items():
            by_signature[(key, signature)]["calls"].add(value)
            if value is not None:
                raw_node_qnames[(key, value)].add(qname)

    nodes = []
    for (key, value), qnames in sorted(raw_node_qnames.items()):
        signatures = set()
        for qname in qnames:
            signature = _pair_signature(groups[qname])
            calls = by_signature[(key, signature)]["calls"]
            if calls == {value}:
                signatures.add(signature)
        node = {
            "node_id": (f"SHARED_BLOCK:{value}" if key[0] == "block"
                        else f"MARKER_CONTEXT:{key[1]}:{value}"),
            "feature_kind": key[0],
            "observed_allele": value,
            "original_read_pair_ids": len(qnames),
            "distinct_consistent_pair_sequence_signatures": len(signatures),
            "is_phased": False,
        }
        if include_qnames:
            node["original_qnames"] = sorted(qnames)
        nodes.append(node)

    result = {
        "schema_version": "ivanka.shared_unphased_evidence.v1",
        "artifact_type": "shared_unphased_evidence_sidecar",
        "shared_block_length": len(allele),
        "shared_block_sha256": hashlib.sha256(allele.encode()).hexdigest(),
        "reference_count": len(references),
        "selected_reference_names": list(references),
        "marker_count": len(markers),
        "strict_original_read_pair_ids_evaluated": len(observations),
        "original_read_pair_qnames_counted_once": True,
        "nodes": nodes,
        "raw_qnames_included": include_qnames,
        "independent_molecules_inferred": False,
        "insert_bases_imputed": False,
        "full_length_haplotype_phase_inferred": False,
        "phase_status": "unidentified",
        "phase_inferred": False,
        "interpretation": (
            "Only directly observed original-read-pair local alleles are "
            "reported. Each original qname pair counted once; sequence-signature "
            "counts exclude missing/conflicting reuses and cannot be interpreted "
            "as physical molecule counts. Marker context does not assign a shared "
            "block to a haplotype; this tool never alters MiCall consensus or 198 "
            "acceptance."),
    }
    if include_direct_links:
        # A direct link is a *single original strict qname* observing
        # the complete local block and one nearby marker at Q15.
        # Incomplete/conflicting copies of the same sequence signature veto
        # that signature's support, even when another copy is complete.
        result["schema_version"] = "ivanka.shared_unphased_evidence_direct.v2"
        result["direct_linkage_observation_scope"] = (
            "same_original_remap_qname_complete_block_and_one_marker")
        result["marker_direct_links"] = []
        for j, marker in enumerate(markers):
            pair_observations = defaultdict(set)
            signatures = defaultdict(set)
            for qname, features in observations.items():
                block = features[("block", 0)]
                allele_call = features[("marker", j)]
                joint = ((block, allele_call) if block is not None
                         and allele_call is not None else None)
                signatures[pair_signatures[qname]].add(joint)
                if joint is not None:
                    pair_observations[joint].add(qname)
            links = []
            for (block, allele_call), qnames in sorted(pair_observations.items()):
                link = {
                    "shared_block_allele": block,
                    "marker_allele": allele_call,
                    "original_pair_ids_directly_observing_both": len(qnames),
                    "consistent_distinct_pair_sequence_signatures": len({
                        pair_signatures[name] for name in qnames
                        if signatures[pair_signatures[name]] == {(block, allele_call)}
                    }),
                    "is_full_length_haplotype_phased": False,
                }
                links.append(link)
            positions = {ref: pos for ref, (pos, _) in
                         sorted(marker["coords"].items())}
            result["marker_direct_links"].append({
                "marker_index": j,
                "reference_positions_zero_based": positions,
                "direct_joint_observation_count": sum(
                    len(qnames) for qnames in pair_observations.values()),
                "direct_joint_distinct_pair_sequence_signatures": sum(
                    len({pair_signatures[name] for name in qnames
                         if signatures[pair_signatures[name]] == {joint}})
                    for joint, qnames in pair_observations.items()),
                "local_block_marker_observations": links,
                "indirect_graph_members_counted_as_direct": False,
                "long_range_haplotype_phase_inferred": False,
            })
        result["direct_linkage_interpretation"] = (
            "Only co-observation by the same original remap read-pair ID. "
            "Pair-sequence signatures are not independent physical molecules. "
            "Partial and conflicting signature reuses are excluded from distinct "
            "signature counts. This is local linkage to exactly one marker, "
            "not complete haplotype phase; gaps and inserts are not imputed.")
    if include_qnames:
        result["original_qname_provenance"] = {
            name: [
                (f"SHARED_BLOCK:{value}" if key[0] == "block"
                 else f"MARKER_CONTEXT:{key[1]}:{value}")
                for key, value in sorted(features.items())
                if value is not None]
            for name, features in sorted(observations.items())
        }
    return result


def _sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("final_conseq_csv", type=Path)
    parser.add_argument("remap_conseq_csv", type=Path)
    parser.add_argument("remap_sam_csv", type=Path)
    parser.add_argument("--region", required=True)
    parser.add_argument("--reference", action="append", required=True)
    parser.add_argument("--mask-start", type=int, required=True)
    parser.add_argument("--mask-end", type=int, required=True)
    parser.add_argument("--anchor", type=int, default=31)
    parser.add_argument("--radius", type=int, default=600)
    parser.add_argument("--min-phred", type=int, default=15)
    parser.add_argument("--direct-links", action="store_true",
                        help="Version 2: observe direct complete-block-to-marker links, no inferred phase")
    parser.add_argument("--include-qnames", action="store_true",
                        help="Explicitly expose original read identifiers in private reports")
    parser.add_argument("--output", type=Path,
                        help="Write versioned JSON sidecar to this path")
    args = parser.parse_args()
    for required in (args.final_conseq_csv, args.remap_conseq_csv, args.remap_sam_csv):
        if not required.is_file():
            parser.error(f"Missing required input: {required}")
    with args.final_conseq_csv.open() as fh:
        rows = [r for r in csv.DictReader(fh)
                if r["region"] == args.region and r["q-cutoff"] == "15"
                and r["consensus-percent-cutoff"] == "MAX"]
    if len(rows) != 1:
        parser.error("Expected exactly one Q15 MAX final region")
    seq = rows[0]["sequence"]
    if (args.mask_start < 0 or args.mask_end <= args.mask_start
            or seq[args.mask_start:args.mask_end] !=
            "x" * (args.mask_end - args.mask_start)):
        parser.error("Selected interval must be an exact lowercase-x mask")
    masked = SimpleNamespace(sequence=seq, start=args.mask_start,
                             end=args.mask_end)
    with args.remap_conseq_csv.open() as fh:
        seeds = {r["region"]: r["sequence"].upper()
                 for r in csv.DictReader(fh)}
    if len(set(args.reference)) != len(args.reference):
        parser.error("Duplicate remap reference")
    try:
        refs = {name: seeds[name] for name in args.reference}
    except KeyError as exc:
        parser.error(f"Missing remap reference {exc}")
    with args.remap_sam_csv.open() as fh:
        report = build_shared_evidence(
            masked, refs, csv.DictReader(fh), args.anchor,
            args.radius, args.min_phred, args.include_qnames,
            args.direct_links)
    report.update({"region": args.region, "mask_start": args.mask_start,
                   "mask_end": args.mask_end})
    report["input_provenance"] = {
        "final_conseq_csv": {"path": str(args.final_conseq_csv),
                              "sha256": _sha256_file(args.final_conseq_csv)},
        "remap_conseq_csv": {"path": str(args.remap_conseq_csv),
                             "sha256": _sha256_file(args.remap_conseq_csv)},
        "remap_sam_csv": {"path": str(args.remap_sam_csv),
                          "sha256": _sha256_file(args.remap_sam_csv)},
    }
    report["minimum_quality"] = args.min_phred
    report["anchor"] = args.anchor
    report["radius"] = args.radius
    out = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out)
    else:
        print(out)



if __name__ == "__main__":
    main()

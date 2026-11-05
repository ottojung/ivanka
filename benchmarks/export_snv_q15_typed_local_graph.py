"""Consume source-bound SNV Q15 node (#175) and direct original-pair link (#176) reports.

Produces a typed local graph with explicit unknown/unobserved edges. Never infers
transitive edges, never concatenates 31-mers to fabricate full-length phased
sequences, never duplicates original QNAME coverage, never treats PCR duplicates
as independent molecules, and never modifies ordinary MiCall MAX/contigs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

NODE_SCHEMA = "ivanka.unphased_snv_original_fastq_q15.v1"
LINK_SCHEMA = "ivanka.snv_q15_direct_original_pair_links.v1"
GRAPH_SCHEMA = "ivanka.snv_q15_typed_local_graph.v1"

REQUIRED_NODE_SOURCE_KEYS = ("audit_tsv", "ordinary_fasta", "original_r1", "original_r2")
DIRECT_ALT_COMBINATIONS = ("alternative_reference", "reference_alternative",
                           "alternative_alternative")
OBSERVED_JOINT_KEYS = ("reference_reference", "alternative_reference",
                       "reference_alternative", "alternative_alternative")


class GraphBuildError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _load_json(path: Path):
    with Path(path).open() as handle:
        return json.load(handle)


def _canonical_json(obj):
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def _require(cond, message):
    if not cond:
        raise GraphBuildError(message)


def _sha(value: str) -> str:
    _require(isinstance(value, str) and len(value) == 64
             and all(c in "0123456789abcdef" for c in value), "invalid SHA256")
    return value


def verify_node_report(report):
    _require(isinstance(report, dict) and report.get("schema_version") == NODE_SCHEMA,
             f"node report must be {NODE_SCHEMA}")
    sources = report.get("source_sha256")
    _require(isinstance(sources, dict), "node report source_sha256 required")
    for key in REQUIRED_NODE_SOURCE_KEYS:
        _sha(sources.get(key))
    candidates = report.get("candidates")
    _require(isinstance(candidates, list), "node candidates required")
    for cand in candidates:
        _require(isinstance(cand, dict), "candidate must be object")
        _require(type(cand.get("parent_fasta_index")) is int, "bad parent_fasta_index")
        _require(type(cand.get("snv_offset_zero_based")) is int, "bad offset")
        _require(cand.get("baseline_base") in "ACGTN", "bad baseline base")
        _require(cand.get("alternate_base") in "ACGTN", "bad alternate base")
        _require(type(cand.get("q15_original_pairs_observing_alternative")) is int,
                 "bad q15_original_pairs_observing_alternative")
        _require(type(cand.get("q15_distinct_consistent_paired_sequences_alternative")) is int,
                 "bad q15_distinct_consistent_paired_sequences_alternative")
        _require(isinstance(cand.get("candidate_meets_local_q15_screen"), bool),
                 "bad candidate_meets_local_q15_screen")
    for flag in ("original_pair_ids_are_independent_physical_molecules",
                 "full_length_haplotype_phase_inferred",
                 "per_haplotype_read_depth_assigned",
                 "modifies_micall_final_max",
                 "changes_198_sample_acceptance"):
        _require(report.get(flag) is False, f"node safety flag {flag} invalid")
    _require(report.get("research_only") is True, "node report must be research_only")
    return report


def verify_link_report(report):
    _require(isinstance(report, dict) and report.get("schema_version") == LINK_SCHEMA,
             f"direct link report must be {LINK_SCHEMA}")
    sources = report.get("source_sha256")
    _require(isinstance(sources, dict), "link report source_sha256 required")
    for key in REQUIRED_NODE_SOURCE_KEYS:
        _sha(sources.get(key))
    qualified = report.get("qualified_unphased_nodes")
    evidence = report.get("direct_allele_link_evidence")
    _require(isinstance(qualified, list), "qualified_unphased_nodes required")
    _require(isinstance(evidence, list), "direct_allele_link_evidence required")
    _require(type(report.get("candidate_pair_count")) is int, "candidate_pair_count required")
    _require(type(report.get("minimum_direct_original_pair_ids_and_signatures")) is int
             and report["minimum_direct_original_pair_ids_and_signatures"] >= 1,
             "minimum_direct_original_pair_ids_and_signatures required")
    _require(type(report.get("minimum_phred_all_31_bases")) is int
             and report["minimum_phred_all_31_bases"] >= 15,
             "minimum_phred_all_31_bases required")
    for item in qualified:
        _require(isinstance(item, dict), "qualified node must be object")
        for key in ("parent_fasta_index", "snv_offset_zero_based"):
            _require(type(item.get(key)) is int, f"qualified node missing {key}")
        for key in ("baseline_base", "alternate_base"):
            _require(item.get(key) in "ACGTN", f"qualified node missing {key}")
        _require(isinstance(item.get("candidate_meets_local_q15_screen"), bool),
                 "qualified node qualification flag required")
    for item in evidence:
        _require(isinstance(item, dict), "edge evidence must be object")
        pair = item.get("candidate_indices_zero_based")
        _require(isinstance(pair, list) and len(pair) == 2
                 and all(type(v) is int and v >= 0 for v in pair)
                 and pair[0] < pair[1], "bad candidate pair")
        for field in ("observed_joint_original_pair_ids",
                      "observed_joint_distinct_consistent_pair_sequences"):
            counts = item.get(field)
            _require(isinstance(counts, dict), f"{field} required")
            for key in OBSERVED_JOINT_KEYS:
                _require(type(counts.get(key)) is int and counts[key] >= 0,
                         f"{field}.{key} required")
        supported = item.get("supported_direct_local_allele_combinations")
        _require(isinstance(supported, list), "supported combinations required")
        _require(all(s in DIRECT_ALT_COMBINATIONS for s in supported),
                 "unsupported combination name")
        _require(len(supported) == len(set(supported)),
                 "duplicate supported allele combination")
        _require(isinstance(item.get("direct_local_link_supported"), bool),
                 "direct_local_link_supported required")
        _require(isinstance(item.get("withheld_for_unqualified_node"), bool),
                 "withheld_for_unqualified_node required")
        _require(item.get("transitive_link_imputed") is False,
                 "transitive_link_imputed must be false")
        _require(item.get("haplotype_phase_inferred") is False,
                 "haplotype_phase_inferred must be false")
        _require(item.get("joint_pair_counts_are_independent_physical_molecules") is False,
                 "joint counts must not claim independent molecules")
    for flag in ("original_pair_ids_are_independent_physical_molecules",
                 "full_length_haplotype_phase_inferred",
                 "per_haplotype_coverage_assigned",
                 "transitive_links_created",
                 "modifies_micall_final_max",
                 "changes_198_acceptance"):
        _require(report.get(flag) is False, f"link safety flag {flag} invalid")
    return report


def bind_reports(node_report, link_report):
    _require(node_report["source_sha256"] == link_report["source_sha256"],
             "node/link source SHA256 mismatch")
    candidates = node_report["candidates"]
    qualified = link_report["qualified_unphased_nodes"]
    _require(len(candidates) == len(qualified),
             "node/link candidate count mismatch")
    _require(len(candidates) == node_report.get("reported_local_snv_candidates"),
             "node reported_local_snv_candidates mismatch")
    expected_pairs = len(candidates) * (len(candidates) - 1) // 2
    _require(len(link_report["direct_allele_link_evidence"]) == expected_pairs
             and link_report["candidate_pair_count"] == expected_pairs,
             "direct link report pair count mismatch")
    _require(node_report.get("pairs_scanned") == link_report.get("original_pairs_scanned"),
             "node/link original pair scan count mismatch")
    _require(node_report.get("q15_minimum_base_quality") ==
             link_report.get("minimum_phred_all_31_bases"),
             "node/link Q15 quality floor mismatch")
    pair_keys = [tuple(e["candidate_indices_zero_based"]) for e in
                 link_report["direct_allele_link_evidence"]]
    _require(len(set(pair_keys)) == expected_pairs,
             "repeated or missing candidate pair evidence")
    _require(all(0 <= i < len(candidates) and 0 <= j < len(candidates)
                 for i, j in pair_keys), "candidate edge index outside node count")
    for e in link_report["direct_allele_link_evidence"]:
        a, b = e["candidate_indices_zero_based"]
        withheld = not (candidates[a]["candidate_meets_local_q15_screen"]
                        and candidates[b]["candidate_meets_local_q15_screen"])
        _require(e["withheld_for_unqualified_node"] is withheld,
                 "edge qualification disagrees with node report")
        for label in OBSERVED_JOINT_KEYS:
            pairs = e["observed_joint_original_pair_ids"][label]
            signatures = e["observed_joint_distinct_consistent_pair_sequences"][label]
            _require(signatures <= pairs, "more signatures than original read pairs")
    for index, (cand, qual) in enumerate(zip(candidates, qualified)):
        for key in ("parent_fasta_index", "snv_offset_zero_based",
                    "baseline_base", "alternate_base",
                    "candidate_meets_local_q15_screen"):
            _require(cand.get(key) == qual.get(key),
                     f"node/link candidate mismatch at {index}:{key}")


def _node_id(sample, cand):
    return (
        f"snv_local::{sample}::parent{cand['parent_fasta_index']}"
        f"::pos{cand['snv_offset_zero_based']}"
        f"::{cand['baseline_base']}>{cand['alternate_base']}"
    )


def _allele_node_id(parent_id, allele_kind):
    return f"{parent_id}::{allele_kind}"


def build_typed_local_graph(*, sample, node_report, link_report,
                            node_report_sha256, link_report_sha256,
                            min_joint_pairs=None, min_consistent_signatures=None):
    node_report = verify_node_report(node_report)
    link_report = verify_link_report(link_report)
    bind_reports(node_report, link_report)

    required_pairs = (link_report["minimum_direct_original_pair_ids_and_signatures"]
                      if min_joint_pairs is None else min_joint_pairs)
    required_sigs = (link_report["minimum_direct_original_pair_ids_and_signatures"]
                     if min_consistent_signatures is None else min_consistent_signatures)
    _require(type(required_pairs) is int and required_pairs >= 1, "min_joint_pairs >= 1")
    _require(type(required_sigs) is int and required_sigs >= 1,
             "min_consistent_signatures >= 1")
    _require(required_pairs >= link_report["minimum_direct_original_pair_ids_and_signatures"],
             "min_joint_pairs cannot weaken link report floor")
    _require(required_sigs >= link_report["minimum_direct_original_pair_ids_and_signatures"],
             "min_consistent_signatures cannot weaken link report floor")

    nodes = []
    edges = []
    unknown = []
    candidates = node_report["candidates"]
    candidate_ids = []
    for cand in candidates:
        cid = _node_id(sample, cand)
        candidate_ids.append(cid)
        if not cand["candidate_meets_local_q15_screen"]:
            unknown.append({
                "kind": "unqualified_snv_candidate_withheld",
                "candidate_node": cid,
                "reason": "candidate_meets_local_q15_screen_false",
                "q15_original_pairs_observing_alternative":
                    cand["q15_original_pairs_observing_alternative"],
                "exact_31mer_uniquely_locates_offset_in_parent":
                    cand.get("exact_31mer_uniquely_locates_offset_in_parent"),
            })
            continue
        nodes.append({
            "id": cid,
            "type": "snv_q15_candidate_site",
            "sample": sample,
            "parent_fasta_index": cand["parent_fasta_index"],
            "snv_offset_zero_based": cand["snv_offset_zero_based"],
            "baseline_base": cand["baseline_base"],
            "alternate_base": cand["alternate_base"],
            "candidate_meets_local_q15_screen": cand["candidate_meets_local_q15_screen"],
            "q15_original_pairs_observing_alternative": cand["q15_original_pairs_observing_alternative"],
            "q15_distinct_consistent_paired_sequences_alternative": cand[
                "q15_distinct_consistent_paired_sequences_alternative"],
            "q15_original_pairs_observing_reference": cand["q15_original_pairs_observing_reference"],
            "q15_distinct_consistent_paired_sequences_reference": cand.get(
                "q15_distinct_consistent_paired_sequences_reference"),
            "q15_original_pairs_with_both_alleles": cand["q15_original_pairs_with_both_alleles"],
            "q15_original_pairs_without_exact_31mer": cand["q15_original_pairs_without_exact_31mer"],
            "exact_31mer_uniquely_locates_offset_in_parent": cand.get(
                "exact_31mer_uniquely_locates_offset_in_parent"),
            "locally_observed_not_haplotype_phased": True,
            "full_length_haplotype_phase_proven": False,
            "independent_physical_molecules_assigned": False,
            "per_haplotype_read_depth_assigned": False,
        })
    for item in link_report["direct_allele_link_evidence"]:
        a, b = item["candidate_indices_zero_based"]
        _require(0 <= a < len(candidate_ids) and 0 <= b < len(candidate_ids),
                 "edge candidate index out of range")
        from_id, to_id = candidate_ids[a], candidate_ids[b]
        observed_ids = item["observed_joint_original_pair_ids"]
        observed_sigs = item["observed_joint_distinct_consistent_pair_sequences"]
        supported = []
        for combo in DIRECT_ALT_COMBINATIONS:
            pair_ids = observed_ids[combo]
            pair_sigs = observed_sigs[combo]
            meets = pair_ids >= required_pairs and pair_sigs >= required_sigs
            allele_a, allele_b = combo.split("_")
            from_allele = _allele_node_id(from_id, allele_a)
            to_allele = _allele_node_id(to_id, allele_b)
            base_edge = {
                "id": f"edge::direct_original_q15_pair::{sample}::{from_allele}::{to_allele}",
                "type": "direct_original_q15_pair_snv_link",
                "from": from_allele,
                "to": to_allele,
                "candidate_sites": [from_id, to_id],
                "allele_combination": combo,
                "observed_joint_original_pair_ids": pair_ids,
                "observed_joint_distinct_consistent_pair_sequences": pair_sigs,
                "same_original_r1_r2_pair_required": True,
                "same_original_strict_read_pair_qname_required": True,
                "q15_required_all_31_bases": True,
                "raw_qnames_disclosed": False,
                "thresholds": {
                    "min_joint_pairs": required_pairs,
                    "min_consistent_signatures": required_sigs,
                },
                "transitive_inference_used": False,
                "transitive_link_imputed": False,
                "haplotype_phase_inferred": False,
                "full_length_haplotype_phase_inferred": False,
                "independent_physical_molecules_inferred": False,
                "per_haplotype_coverage_assigned": False,
                "fabricated_full_length_sequence": False,
                "modifies_micall_final_max": False,
                "changes_198_acceptance": False,
            }
            if item["withheld_for_unqualified_node"] or not meets:
                status = ("withheld_for_unqualified_node"
                          if item["withheld_for_unqualified_node"]
                          else "insufficient_direct_support")
                # Rejected combinations do not belong in the graph's
                # *edges* collection, even as status=false placeholders.
                unknown.append({
                    "kind": status,
                    "edge_id": base_edge["id"],
                    "candidate_sites": [from_id, to_id],
                    "from": from_allele,
                    "to": to_allele,
                    "allele_combination": combo,
                    "observed_joint_original_pair_ids": pair_ids,
                    "observed_joint_distinct_consistent_pair_sequences": pair_sigs,
                    "direct_local_link_supported": False,
                    "transitive_link_imputed": False,
                })
            else:
                if from_allele not in {n["id"] for n in nodes}:
                    nodes.append({
                        "id": from_allele,
                        "type": "snv_q15_observed_allele_node",
                        "candidate_site": from_id,
                        "allele_kind": allele_a,
                        "sequence_31mer_observed": False,
                        "observed_only_as_q15_direct_evidence": True,
                        "full_length_haplotype_phase_proven": False,
                        "independent_physical_molecules_assigned": False,
                    })
                if to_allele not in {n["id"] for n in nodes}:
                    nodes.append({
                        "id": to_allele,
                        "type": "snv_q15_observed_allele_node",
                        "candidate_site": to_id,
                        "allele_kind": allele_b,
                        "sequence_31mer_observed": False,
                        "observed_only_as_q15_direct_evidence": True,
                        "full_length_haplotype_phase_proven": False,
                        "independent_physical_molecules_assigned": False,
                    })

                edges.append(dict(base_edge, status="direct_local_link_supported",
                                  direct_local_link_supported=True))
                supported.append(combo)

        reported_supported = item["supported_direct_local_allele_combinations"]
        _require(set(supported) == set(reported_supported),
                 "supported_direct_local_allele_combinations disagrees with thresholds/report")
        _require(item["direct_local_link_supported"] == bool(supported),
                 "direct_local_link_supported disagrees with supported combinations")
        ref_ids = observed_ids["reference_reference"]
        ref_sigs = observed_sigs["reference_reference"]
        if ref_ids or ref_sigs:
            unknown.append({
                "kind": "reference_reference_coobservation_not_variant_link",
                "candidate_sites": [from_id, to_id],
                "observed_joint_original_pair_ids": ref_ids,
                "observed_joint_distinct_consistent_pair_sequences": ref_sigs,
            })

    unknown.append({
        "kind": "phase_unknown",
        "full_length_haplotype_phase_inferred": False,
        "independent_physical_molecules_assigned": False,
        "transitive_path_edges_emitted": False,
        "fabricated_full_length_sequences": False,
    })
    _require(not any(e.get("transitive_link_imputed") for e in edges),
             "transitive edges are forbidden")
    graph = {
        "schema_version": GRAPH_SCHEMA,
        "artifact_type": "snv_q15_typed_local_graph",
        "edge_semantics": "Only qualified direct original-Q15-pair links occur in edges; rejected pairs live in negative_unknown",
        "source_verification": {
            "report_sha256s_recorded_not_independently_checked_by_builder": True,
            "original_fastqs_replayed_in_graph_builder": False,
            "original_pair_counts_inherited_from_source_pinned_reports": True,
            "sample_label_independently_authenticated": False,
            "caller_pinned_report_bytes_checked_by_cli": False,
        },
        "sample": sample,
        "source_reports": {
            "node_report_175_schema": node_report.get("schema_version"),
            "node_report_175_sha256": node_report_sha256,
            "direct_link_report_176_schema": link_report.get("schema_version"),
            "direct_link_report_176_sha256": link_report_sha256,
            "source_sha256": node_report["source_sha256"],
        },
        "thresholds": {
            "minimum_phred_all_31_bases": link_report["minimum_phred_all_31_bases"],
            "minimum_direct_original_pair_ids_and_signatures": required_pairs,
            "min_consistent_signatures": required_sigs,
            "pairs_scanned_node_report": node_report.get("pairs_scanned"),
            "pairs_scanned_link_report": link_report.get("original_pairs_scanned"),
        },
        "nodes": nodes,
        "edges": edges,
        "negative_unknown": unknown,
        "safety": {
            "original_reads_fastq_modified": False,
            "original_micall_max_modified": False,
            "affects_198_acceptance": False,
            "affects_iva_baselines": False,
            "affects_reference_panel_or_gates": False,
            "independent_physical_molecules_claimed": False,
            "full_length_haplotype_phase_claimed": False,
            "transitive_inference_used": False,
            "fabricated_full_length_sequences": False,
        },
        "interpretation": (
            "Typed local graph consumed from source-bound SNV Q15 node and direct "
            "original paired-read link reports. Supported alternative-containing "
            "edges require the same original R1/R2 Q15 pair evidence and "
            "distinct consistent paired-sequence support. Reference/reference "
            "co-observation is never a variant edge. No transitive closure, no "
            "PCR-duplicate-as-molecule claims, no full-length phased sequence "
            "fabrication, and no MiCall MAX/198/IVA/reference/gate changes."
        ),
    }
    return graph


def _private_write(path: Path, content: str, protected_roots):
    dest = Path(path).resolve()
    for root in protected_roots:
        if not root:
            continue
        resolved = Path(root).resolve()
        if dest == resolved or resolved in dest.parents:
            raise GraphBuildError(f"refusing output inside protected source: {resolved}")
    if dest.exists():
        raise GraphBuildError("refusing to overwrite existing output")
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(content)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-report", type=Path, required=True)
    parser.add_argument("--direct-link-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample", required=True)
    parser.add_argument("--expected-node-report-sha256", required=True)
    parser.add_argument("--expected-direct-link-report-sha256", required=True)
    parser.add_argument("--min-joint-pairs", type=int)
    parser.add_argument("--min-consistent-signatures", type=int)
    parser.add_argument("--protect-root", action="append", default=[], type=Path)
    args = parser.parse_args(argv)

    node_sha = sha256_file(args.node_report)
    link_sha = sha256_file(args.direct_link_report)
    _require(node_sha == args.expected_node_report_sha256, "node report SHA256 mismatch")
    _require(link_sha == args.expected_direct_link_report_sha256,
             "direct link report SHA256 mismatch")
    graph = build_typed_local_graph(
        sample=args.sample,
        node_report=_load_json(args.node_report),
        link_report=_load_json(args.direct_link_report),
        node_report_sha256=node_sha,
        link_report_sha256=link_sha,
        min_joint_pairs=args.min_joint_pairs,
        min_consistent_signatures=args.min_consistent_signatures,
    )
    graph["source_verification"]["caller_pinned_report_bytes_checked_by_cli"] = True
    protected = [args.node_report.parent, args.direct_link_report.parent,
                 *args.protect_root]
    _private_write(args.output, _canonical_json(graph), protected)
    print(_canonical_json({
        "ok": True,
        "schema_version": GRAPH_SCHEMA,
        "output": str(args.output.resolve()),
        "sample": graph["sample"],
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "negative_unknown": len(graph["negative_unknown"]),
        "affects_198_acceptance": False,
    }), end="")


if __name__ == "__main__":
    try:
        main()
    except (GraphBuildError, ValueError, OSError, json.JSONDecodeError,
            KeyError, TypeError) as exc:
        raise SystemExit(f"ERROR: {exc}")

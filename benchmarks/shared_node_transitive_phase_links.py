"""Explicit shared-sequence nodes with original read-pair provenance and
observed SNP/anchor associations, without inferred haplotype phase.

A node is an observed feature (e.g. a shared block edge/allele or a
marker/anchor allele). An undirected edge between nodes exists only if the
SAME strict read pair with original paired-read provenance observes both
nodes with unambiguous bases; unsequenced inserts are never imputed and
missing observations break the chain. Identical paired-read sequences are
not independent molecules (counted by pair signature). The connected
component implies transitive observed co-association via read-pair edges
and does not prove a single haplotype order across long gaps
without direct bridging; uncertainty is reported explicitly.
"""
from collections import defaultdict
import argparse
import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from shared_block_phase_links import discover_markers
from shared_block_consensus_candidate import (
    _pair_signature,
    _strict_pair,
    canonical_base,
)
from shared_locus_remap_coverage import sam_observations

BASES = frozenset("ACGT")


class PhaseGraph:
    def __init__(self):
        self.adj = defaultdict(set)
        self.node_pairs = defaultdict(set)  # node -> set of pair_ids that connect to it
        self.pair_nodes = defaultdict(set)  # pair_id/signature-based identity -> nodes


def audit_transitive_links(masked, references, rows, anchor=31, radius=600,
                           minimum_quality=15, edge_lengths=(1, 4, 8, 16, 36)):
    allele, loci, markers = discover_markers(masked, references, anchor, radius)
    requested = sorted(set(k for k in (*edge_lengths, len(allele))
                           if 1 <= k <= len(allele)))
    coords = {name: dict(v) for name, v in loci.items()}
    for j, marker in enumerate(markers):
        for name, (pos, base) in marker["coords"].items():
            coords[name][pos] = (len(allele) + j, base)
    groups = defaultdict(list)
    for row in rows:
        groups[row["qname"]].append(row)

    # Build graph over nodes: block edge segments and markers
    graph = PhaseGraph()
    # Track per (pair, node) observations
    pair_node_obs = defaultdict(dict)  # pair_qname -> {node_id: (base_or_tuple,...)}
    pair_sigs = {}

    for qname, pair in groups.items():
        if not _strict_pair(pair) or pair[0]["rname"] not in coords:
            continue
        name = pair[0]["rname"]
        try:
            signature = _pair_signature(pair)
        except Exception:
            continue
        pair_sigs[qname] = signature
        observed = defaultdict(set)  # site -> set of bases
        for row in pair:
            for site, base, _, expected in sam_observations(
                    row, coords[name], minimum_quality):
                canonical = (allele[site] if site < len(allele)
                             else markers[site - len(allele)]["alleles"][name])
                try:
                    cbase = canonical_base(base, expected, canonical)
                except Exception:
                    continue
                observed[site].add(cbase)
        # Record complete block observations
        if all(len(observed[i]) == 1 for i in range(len(allele))):
            block_allele = "".join(next(iter(observed[i])) for i in range(len(allele)))
            node_id = f"BLOCK:{block_allele}"
            pair_node_obs[qname][node_id] = block_allele
        # Record marker observations
        for j, marker in enumerate(markers):
            msite = len(allele) + j
            if len(observed[msite]) == 1:
                mbase = next(iter(observed[msite]))
                node_id = f"MARKER:{j}:{mbase}"
                pair_node_obs[qname][node_id] = mbase
        # Record partial block edge observations (prefix/suffix as appropriate)
        # For general linkage, track contiguous observed edges
        # prefix from left
        prefix_run = []
        for i in range(len(allele)):
            if len(observed[i]) == 1:
                prefix_run.append(next(iter(observed[i])))
            else:
                break
        for k in requested:
            if len(prefix_run) >= k:
                node_id = f"BLOCK_EDGE_PREFIX:{k}:{''.join(prefix_run[:k])}"
                pair_node_obs[qname][node_id] = ''.join(prefix_run[:k])
        # suffix from right
        suffix_run = []
        for i in range(len(allele) - 1, -1, -1):
            if len(observed[i]) == 1:
                suffix_run.append(next(iter(observed[i])))
            else:
                break
        for k in requested:
            if len(suffix_run) >= k:
                node_id = f"BLOCK_EDGE_SUFFIX:{k}:{''.join(reversed(suffix_run[:k]))}"
                pair_node_obs[qname][node_id] = ''.join(reversed(suffix_run[:k]))

    # Build edges: pairs that co-observe multiple nodes
    for qname, nodes in pair_node_obs.items():
        if len(nodes) < 2:
            continue
        node_list = list(nodes.keys())
        for idx_i in range(len(node_list)):
            ni = node_list[idx_i]
            for idx_j in range(idx_i + 1, len(node_list)):
                nj = node_list[idx_j]
                graph.adj[ni].add(nj)
                graph.adj[nj].add(ni)
                graph.node_pairs[ni].add(qname)
                graph.node_pairs[nj].add(qname)
                graph.pair_nodes[qname].add(ni)
                graph.pair_nodes[qname].add(nj)

    # Find connected components
    visited = set()
    components = []
    for start in graph.adj:
        if start in visited:
            continue
        # BFS
        stack = [start]
        visited.add(start)
        comp = {start}
        i = 0
        while i < len(stack):
            cur = stack[i]
            i += 1
            for nbr in graph.adj[cur]:
                if nbr not in visited:
                    visited.add(nbr)
                    stack.append(nbr)
                    comp.add(nbr)
        if comp:
            components.append(comp)

    # Distinguish direct full-block evidence from short-edge co-observations.
    # A graph component is only a co-occurrence relation; counting every pair
    # in it as marker-linked would manufacture hundreds of "witnesses" from a
    # small number of direct bridging observations.
    marker_linkages = []
    for j, marker in enumerate(markers):
        marker_prefix = f"MARKER:{j}:"
        direct_pairs = set()
        full_observations = defaultdict(set)
        full_by_signature = defaultdict(set)
        for qname, observations in pair_node_obs.items():
            marker_bases = {n[len(marker_prefix):] for n in observations
                            if n.startswith(marker_prefix)}
            block_alleles = {n[len("BLOCK:"):] for n in observations
                             if n.startswith("BLOCK:")}
            has_edge = any(n.startswith("BLOCK_EDGE_") for n in observations)
            if marker_bases and (block_alleles or has_edge):
                direct_pairs.add(qname)
            for allele in marker_bases:
                for block in block_alleles:
                    full_observations[(block, allele)].add(qname)
                    full_by_signature[pair_sigs[qname]].add((block, allele))

        # A sequence signature with incompatible witnessed alleles is
        # unresolved, never counted twice as independent evidence.
        valid_full_signatures = {sig: next(iter(values))
                                 for sig, values in full_by_signature.items()
                                 if len(values) == 1}
        full_spectrum = [{
            "shared_block": block, "marker_base": allele,
            "read_pair_ids": len(qnames),
            "distinct_pair_sequences": sum(
                observed == (block, allele)
                for observed in valid_full_signatures.values()),
        } for (block, allele), qnames in sorted(full_observations.items())]

        eligible_components = []
        conflicting_components = 0
        associated_pairs = set()
        for comp in components:
            marker_bases = {n[len(marker_prefix):] for n in comp
                            if n.startswith(marker_prefix)}
            block_alleles = {n[len("BLOCK:"):] for n in comp
                             if n.startswith("BLOCK:")}
            contains_edge = any(n.startswith("BLOCK_EDGE_") for n in comp)
            if not marker_bases or not (block_alleles or contains_edge):
                continue
            if len(marker_bases) > 1 or len(block_alleles) > 1:
                conflicting_components += 1
                continue
            eligible_components.append(comp)
            for n in comp:
                associated_pairs.update(graph.node_pairs[n])

        # These are graph membership counts, not direct evidence, and not
        # independent molecules; no indirect component membership is counted
        # toward a phase witness threshold.
        direct_signatures = {
            pair_sigs[qname] for qname in direct_pairs
            if qname in pair_sigs
        }
        marker_linkages.append({
            "offset_from_block_start": marker["offset"],
            "reference_marker_alleles": marker["alleles"],
            "direct_edge_or_full_read_pair_ids": len(direct_pairs),
            "direct_edge_or_full_distinct_pair_sequences":
                len(direct_signatures),
            "direct_full_block_read_pair_ids":
                len(set().union(*full_observations.values())
                    if full_observations else set()),
            "direct_full_block_distinct_pair_sequences":
                len(valid_full_signatures),
            "direct_full_block_observed_linkages": full_spectrum,
            "nonconflicting_components": len(eligible_components),
            "competing_allele_components": conflicting_components,
            "co_component_read_pair_ids_not_phase_evidence":
                len(associated_pairs - direct_pairs),
            "uncertainty": (
                "Only same-pair full-block+marker co-observation constitutes "
                "direct full-local-block linkage. Short block edges and "
                "transitive component membership do not prove phase, "
                "independent molecules, or haplotype order."),
        })

    return {
        "shared_block_length": len(allele),
        "complete_block_pair_ids": sum(1 for qname, nodes in pair_node_obs.items()
                                       if any(n.startswith("BLOCK:") for n in nodes)),
        "shared_block_sha256": hashlib.sha256(allele.encode()).hexdigest(),
        "marker_anchor": anchor,
        "marker_search_radius": radius,
        "nodes_observed": len(set().union(*pair_node_obs.values()) if pair_node_obs else set()),
        "edges": sum(len(v) for v in graph.adj.values()) // 2,
        "components": len(components),
        "markers": marker_linkages,
        "interpretation": ("Graph of observed shared-sequence features. "
                          "Only direct full-block-to-marker observations are "
                          "reported as full-local-block linkage. Short-edge "
                          "and indirect graph associations are not phase "
                          "witnesses and are never counted toward coverage "
                          "or molecule independence. No imputed insert bases."),
    }


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
    args = parser.parse_args()
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
        parser.error("Selected interval is not an exact lowercase-x mask")
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
        report = audit_transitive_links(masked, refs, csv.DictReader(fh),
                                        args.anchor, args.radius, args.min_phred)
    report.update({"region": args.region, "mask_start": args.mask_start,
                   "mask_end": args.mask_end})
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

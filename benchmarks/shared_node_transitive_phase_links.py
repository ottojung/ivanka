"""Explicit shared-sequence nodes with original read-pair provenance and
transitive observed SNP/anchor phase linkage.

A node is an observed feature (e.g. a shared block edge/allele or a
marker/anchor allele). An undirected edge between nodes exists only if the
SAME strict read pair with original paired-read provenance observes both
nodes with unambiguous bases; unsequenced inserts are never imputed and
missing observations break the chain. Identical paired-read sequences are
not independent molecules (counted by pair signature). The connected
component implies transitive observed co-association via read-pair edges
but does not by itself prove a single haplotype order across long gaps
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
        self.node_pair_sigs = defaultdict(lambda: defaultdict(set))  # node -> sig -> witness info

    def add_observation(self, pair_key, sig_key, node_id, base_witness=None):
        # pair_key is the original read pair identity; sig_key is for deduplication
        self.pair_nodes[pair_key].add(node_id)
        self.node_pairs[node_id].add(pair_key)
        if base_witness is not None and sig_key is not None:
            self.node_pair_sigs[node_id][sig_key].add(base_witness)


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
        sig = pair_sigs.get(qname)
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
                graph.node_pair_sigs[ni][sig].add(nodes[ni] if ni in nodes else None)
                graph.node_pair_sigs[nj][sig].add(nodes[nj] if nj in nodes else None)

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

    # Compute transitive linkages between block components and markers
    marker_linkages = []
    for j, marker in enumerate(markers):
        marker_nodes = [n for n in graph.adj if n.startswith(f"MARKER:{j}:")]
        # Find which pairs connect block-edges/prefix/suffix to this marker via paths
        direct_pairs = set()
        transitive_pairs = set()
        pair_to_path = defaultdict(list)
        # Direct: same pair observes both a block node and marker node
        for qname in graph.pair_nodes:
            qnodes = graph.pair_nodes[qname]
            has_marker = any(n in marker_nodes for n in qnodes)
            has_block = any((n.startswith("BLOCK:") or n.startswith("BLOCK_EDGE")) for n in qnodes)
            if has_marker and has_block:
                direct_pairs.add(qname)
                pair_to_path[qname] = ["direct"]
        # Transitive: pairs connected through graph path of length > 1
        # A pair observes some node A; another pair observes A and B etc., but we need
        # to track original read-pair provenance - each edge must come from some read pair
        # that observed both endpoints. Transitive linkage means marker is in same connected
        # component as block nodes via edges where each edge is supported by some read pair
        # (possibly different). But we must be careful not to count repeated alignments as
        # independent molecules - we track by original pair signatures.
        # Find components that contain both block and marker nodes
        transitive_components = []
        for comp in components:
            has_marker_c = any(n in marker_nodes for n in comp)
            has_block_c = any((n.startswith("BLOCK:") or n.startswith("BLOCK_EDGE")) for n in comp)
            if has_marker_c and has_block_c:
                transitive_components.append(comp)
                # Count all original read pairs that participate in any edge of this component
                comp_pairs = set()
                for n in comp:
                    comp_pairs.update(graph.node_pairs[n])
                # But exclude those already counted as direct? Direct means same pair observes both
                for cp in comp_pairs:
                    if cp not in direct_pairs:  # only add if not direct same-pair observation
                        transitive_pairs.add(cp)
                        pair_to_path[cp] = ["transitive_via_component"]

        # Deduplicate by pair signature to avoid counting repeated alignments as independent molecules
        all_linking_pairs = direct_pairs | transitive_pairs
        # Group by signature
        sig_to_pairs = defaultdict(set)
        for qname in all_linking_pairs:
            sig = pair_sigs.get(qname)
            if sig is not None:
                sig_to_pairs[sig].add(qname)
            else:
                sig_to_pairs[qname].add(qname)  # should not happen

        marker_linkages.append({
            "offset_from_block_start": marker["offset"],
            "reference_marker_alleles": marker["alleles"],
            "direct_linked_read_pair_ids": len(direct_pairs),
            "direct_linked_distinct_pair_sequences": len(sig_to_pairs) if all_linking_pairs else 0,
            "transitive_linked_read_pair_ids": len(transitive_pairs),
            "total_linked_read_pair_ids": len(all_linking_pairs),
            "total_linked_distinct_pair_sequences": sum(1 for sig, pairs in sig_to_pairs.items()
                                                        if pairs) if False else len([s for s in sig_to_pairs if sig_to_pairs[s]]),  # count distinct sigs that appear in linking
            "linking_pair_signatures": len([s for s, plist in sig_to_pairs.items() if any(p in all_linking_pairs for p in plist)]),
            "transitive_components_containing_both": len(transitive_components),
            "no_direct_observation_same_pair": len(direct_pairs) == 0 and len(transitive_pairs) > 0,
            "uncertainty": ("Transitive edges require only that different pairs connect nodes in the graph; "
                            "this indicates observed co-occurrence via shared sequence features, "
                            "not necessarily a single uninterrupted haplotype or molecule order without direct bridging evidence.")
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
        "interpretation": ("Graph of explicit shared-sequence nodes with original read-pair provenance. "
                          "Edges between nodes require same strict pair observing both (with unambiguous bases); "
                          "transitive connectivity across different pairs is reported separately with uncertainty. "
                          "No imputed insert bases; repeated alignments counted by pair signature only."),
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

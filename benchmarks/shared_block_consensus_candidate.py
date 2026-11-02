"""Read-only candidate for a *shared* local consensus, not per-haplotype depth.

Never modifies MiCall calls or the 100-depth rule. A qname is a read-pair ID,
not an independent original molecule. This module is an experiment, not a fix.
"""
from collections import defaultdict

COMPLEMENT = str.maketrans("ACGT", "TGCA")
BASES = frozenset("ACGT")


def _complete_block_evidence(by_site, shared_allele, pair_signatures):
    """Count directly observed complete local alleles, never inferred inserts.

    A pair must have an unambiguous observed base at *every* block site.
    This does not require the 31bp external flanks or prove long-range phase.
    Reused paired-sequence signatures with partial or contradictory evidence
    cannot contribute to distinct full-block support.
    """
    observed = defaultdict(dict)
    for site, pairs in enumerate(by_site):
        for qname, bases in pairs.items():
            observed[qname][site] = next(iter(bases)) if len(bases) == 1 else None
    complete = {}
    for qname, sites in observed.items():
        if len(sites) == len(shared_allele) and all(
                sites.get(i) is not None for i in range(len(shared_allele))):
            complete[qname] = "".join(sites[i] for i in range(len(shared_allele)))
    signatures = None
    distinct_allele_counts = defaultdict(int)
    if pair_signatures is not None:
        grouped = defaultdict(set)
        for qname in observed:
            if qname not in pair_signatures:
                raise ValueError("Missing paired-read sequence provenance")
            grouped[pair_signatures[qname]].add(complete.get(qname))
        for values in grouped.values():
            if len(values) == 1 and None not in values:
                distinct_allele_counts[next(iter(values))] += 1
        signatures = {
            "complete_distinct_pair_sequences": sum(
                len(values) == 1 and None not in values
                for values in grouped.values()),
            "shared_allele_distinct_pair_sequences": sum(
                values == {shared_allele} for values in grouped.values()),
            "ambiguous_or_partial_pair_sequences": sum(
                len(values) != 1 or None in values
                for values in grouped.values()),
        }
    allele_counts = defaultdict(int)
    for allele in complete.values():
        allele_counts[allele] += 1
    spectrum = [
        {"sequence": allele, "read_pair_ids": n,
         "distinct_pair_sequences": (distinct_allele_counts[allele]
                                     if pair_signatures is not None else None)}
        for allele, n in sorted(allele_counts.items(),
                               key=lambda item: (-item[1], item[0]))
    ]
    return {
        "observed_complete_local_sequences": spectrum,
        "complete_read_pair_ids": len(complete),
        "shared_allele_complete_read_pair_ids": sum(
            allele == shared_allele for allele in complete.values()),
        "alternative_complete_read_pair_ids": sum(
            allele != shared_allele for allele in complete.values()),
        "distinct_pair_sequence_evidence": signatures,
        "interpretation": "Observed every block base on one read pair; not "
                          "31bp-flank bridging or long-range haplotype phase.",
    }


def canonical_base(base, reference_base, shared_base):
    """Normalize a SAM base from a forward or reverse exact shared locus."""
    if base not in BASES or shared_base not in BASES:
        raise ValueError("Unresolved observed or shared base")
    if reference_base == shared_base:
        return base
    if reference_base == shared_base.translate(COMPLEMENT):
        return base.translate(COMPLEMENT)
    raise ValueError("Reference locus disagrees with shared allele")


def candidate_from_calls(shared_allele, calls, required_depth=100,
                         pair_signatures=None):
    """Compute read-derived calls without treating them as haplotype-specific.

    calls: (site, qname, base) with base already in shared orientation.
    Conflicting observations for one qname/site are discarded completely.
    A site qualifies only if the shared allele has >=required_depth distinct
    qnames, a strict majority, and no alternative reaches required_depth.
    All positions must qualify; no partial consensus is emitted.
    """
    if not shared_allele or set(shared_allele) - BASES or required_depth < 1:
        raise ValueError("Invalid shared allele or depth")
    by_site = [defaultdict(set) for _ in shared_allele]
    for site, qname, base in calls:
        if not isinstance(site, int) or not 0 <= site < len(shared_allele):
            raise ValueError("Observation outside shared block")
        if not isinstance(qname, str) or not qname or base not in BASES:
            raise ValueError("Invalid read-pair ID or base")
        by_site[site][qname].add(base)
    positions = []
    for i, expected in enumerate(shared_allele):
        counts = {b: 0 for b in "ACGT"}
        conflicting = 0
        for bases in by_site[i].values():
            if len(bases) != 1:
                conflicting += 1
            else:
                counts[next(iter(bases))] += 1
        depth = sum(counts.values())
        # Identical paired-read sequences from different qnames are not
        # independent evidence. Count each sequence signature at most once,
        # rejecting signatures associated with contradictory bases.
        distinct = None
        shared_distinct = None
        conflicting_signatures = None
        if pair_signatures is not None:
            by_signature = defaultdict(set)
            for qname, bases in by_site[i].items():
                if qname not in pair_signatures:
                    raise ValueError("Missing paired-read sequence provenance")
                by_signature[pair_signatures[qname]].update(bases)
            unique_counts = {b: 0 for b in "ACGT"}
            for bases in by_signature.values():
                if len(bases) == 1:
                    unique_counts[next(iter(bases))] += 1
            distinct = sum(unique_counts.values())
            shared_distinct = unique_counts[expected]
            conflicting_signatures = len(by_signature) - distinct
        winner = max(counts, key=counts.get)
        runner_up = max(counts[b] for b in BASES if b != expected)
        accepted = (counts[expected] >= required_depth
                    and counts[expected] * 2 > depth
                    and runner_up < required_depth
                    and (shared_distinct is None
                         or shared_distinct >= required_depth))
        positions.append({"site": i, "depth_qnames": depth,
                          "shared_base_qnames": counts[expected],
                          "other_base_qnames": depth-counts[expected],
                          "conflicting_qnames": conflicting,
                          "distinct_pair_sequences": distinct,
                          "shared_base_distinct_pair_sequences": shared_distinct,
                          "conflicting_pair_sequences": conflicting_signatures,
                          "allele_qnames": counts,
                          "read_major_base": winner if counts[winner] * 2 > depth else None,
                          "eligible": accepted})
    complete_block = _complete_block_evidence(by_site, shared_allele, pair_signatures)
    eligible = all(p["eligible"] for p in positions)
    return {"eligible": eligible,
            "sequence_diversity_guard_applied": pair_signatures is not None,
            "read_derived_candidate": "".join(
                p["read_major_base"] for p in positions) if eligible else None,
            "positions": positions,
            "complete_block_observations": complete_block,
            "interpretation": "Pooled local evidence, not per-haplotype depth; "
                              "never write candidate to MiCall consensus."}


def _strict_pair(rows):
    """Require two consistent primary proper mates; never assume TLEN signs."""
    if len(rows) != 2:
        return False
    a, b = sorted(rows, key=lambda r: int(r["flag"]) & 0x80)
    fa, fb = int(a["flag"]), int(b["flag"])
    forbidden = 0x4 | 0x8 | 0x100 | 0x400 | 0x800
    if (fa | fb) & forbidden or (fa & 0x43) != 0x43 or (fb & 0x83) != 0x83:
        return False
    if (fa & 0x80) or (fb & 0x40):
        return False
    if a["rname"] != b["rname"] or a["rnext"] not in ("=", a["rname"]):
        return False
    if b["rnext"] not in ("=", b["rname"]):
        return False
    if a["pnext"] != b["pos"] or b["pnext"] != a["pos"]:
        return False
    return (bool(fa & 0x10) != bool(fb & 0x10)
            and bool(fa & 0x20) == bool(fb & 0x10)
            and bool(fb & 0x20) == bool(fa & 0x10))


def _pair_signature(rows):
    """Orientation-normalized original mate sequences; not molecule IDs."""
    ordered = sorted(rows, key=lambda r: int(r["flag"]) & 0x80)
    result = []
    for row in ordered:
        seq = row["seq"].upper()
        if not seq or set(seq) - set("ACGTN"):
            raise ValueError("Invalid paired-read sequence")
        if int(row["flag"]) & 0x10:
            seq = seq.translate(str.maketrans("ACGTN", "TGCAN"))[::-1]
        result.append(seq)
    return tuple(result)


def audit_remap(masked, references, sam_rows, minimum_quality=15,
                required_depth=100):
    """Exact shared-flank check and strict two-mate Q15 SAM observations."""
    from shared_locus_remap_coverage import group_loci, sam_observations
    allele, loci = group_loci(masked, references)
    groups = defaultdict(list)
    for row in sam_rows:
        groups[row["qname"]].append(row)
    calls = []
    pair_signatures = {}
    for rows in groups.values():
        if not _strict_pair(rows) or rows[0]["rname"] not in loci:
            continue
        pair_signatures[rows[0]["qname"]] = _pair_signature(rows)
        for row in rows:
            for site, base, qname, expected in sam_observations(
                    row, loci[row["rname"]], minimum_quality):
                calls.append((site, qname,
                              canonical_base(base, expected, allele[site])))
    return candidate_from_calls(allele, calls, required_depth,
                                pair_signatures=pair_signatures)

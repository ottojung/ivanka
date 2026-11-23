"""Direct Q15 paired-read evidence, with missing duplicate signatures vetoed.

A sequence signature only supports a pair of loci when *every* original
QNAME carrying those two identical mate sequences has the same complete
pair of direct local observations. Missing and conflicting copies veto it.
"""
from collections import Counter, defaultdict
from itertools import combinations


def count_direct_links(records, admissible_groups):
    pair_counts = defaultdict(Counter)
    signature_counts = Counter()
    signatures = defaultdict(dict)
    for signature, calls in records:
        signature_counts[signature] += 1
        observed = sorted((gid, allele) for gid, allele in calls.items()
                          if gid in admissible_groups)
        for (a, a_allele), (b, b_allele) in combinations(observed, 2):
            if a == b:
                continue
            edge, event = (a, b), (a_allele, b_allele)
            pair_counts[edge][event] += 1
            previous = signatures[edge].get(signature)
            if previous is None:
                signatures[edge][signature] = [event, 1, True]
            else:
                previous[1] += 1
                previous[2] &= previous[0] == event
    distinct = {}
    for edge, observations in signatures.items():
        distinct[edge] = Counter(
            event for signature, (event, n, consistent) in observations.items()
            if consistent and n == signature_counts[signature])
    return pair_counts, distinct

"""Versioned read-quality and coverage models for synthetic benchmark cases.

The committed quality profile is aggregate-only: no source reads or IDs.
Insert-size mixtures remain explicitly modeled assumptions, not calibration.
"""
import json
from functools import lru_cache
from math import ceil
from pathlib import Path

PROFILE = Path(__file__).parent / "references/real-read-quality-20261117.json"
LOW_DEPTH_X = (3, 6, 12, 24)
READ_LENGTH = 150


@lru_cache(maxsize=1)
def quality_profile():
    data = json.loads(PROFILE.read_text())
    if (data.get("schema") != "ivanka.synthetic.quality_profile.v1"
            or data.get("read_length") != READ_LENGTH
            or len(data.get("cycle_quantiles", [])) != 2):
        raise ValueError("unrecognized empirical quality profile")
    profiles = data["cycle_quantiles"]
    if any(len(mate) != READ_LENGTH or any(
            len(row) != 8 or any(type(q) is not int or not 0 <= q <= 41
                                  for q in row) for row in mate)
           for mate in profiles):
        raise ValueError("invalid quality quantile data")
    return data


def quality_values(rng, mate):
    """Sample correlated quality quantile bands from aggregate real reads."""
    if mate not in (1, 2):
        raise ValueError("mate must be 1 or 2")
    rows = quality_profile()["cycle_quantiles"][mate - 1]
    band = rng.randrange(8)
    result = []
    for i, quantiles in enumerate(rows):
        if i and i % 25 == 0 and rng.random() < 0.4:
            band = rng.randrange(8)
        result.append(quantiles[band])
    return result


def low_depth_pair_count(genome_length, seed, normal_pairs):
    """3x/6x/12x/24x nominal coverage, balanced over 16 fixed seeds."""
    depth = LOW_DEPTH_X[seed % len(LOW_DEPTH_X)]
    total = min(normal_pairs, max(20, ceil(depth * genome_length /
                                          (2 * READ_LENGTH))))
    return total, depth


def insert_length(rng, family):
    """Prespecified fragment mixture (not fitted from the quality archive)."""
    if family == "overlapping_mates":
        return 185
    if family == "long_inserts":
        return rng.randrange(500, 641)
    mode = rng.random()
    if mode < 0.75:
        mean, spread = 270, 24
    elif mode < 0.93:
        mean, spread = 210, 22
    else:
        mean, spread = 400, 50
    return max(150, min(600, round(rng.gauss(mean, spread))))

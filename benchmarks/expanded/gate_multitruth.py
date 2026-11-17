"""Fail-closed checks for each >=15% synthetic truth's final MiCall score."""
import math

SCALE = 10000


def check_sample(sample, results, competitors, minimum_ratio):
    errors = []
    known = None
    scores = {}
    for name, outcome in results.items():
        rows = outcome.get("per_truth")
        if not isinstance(rows, dict) or not rows:
            errors.append(f"{sample}:{name}:missing_per_truth")
            continue
        identities = {}
        values = {}
        for key, item in rows.items():
            if not isinstance(item, dict):
                errors.append(f"{sample}:{name}:invalid_truth_row")
                break
            raw, length, fraction = (item.get("score"), item.get("length"),
                                     item.get("fraction"))
            digest, abundance = (item.get("truth_sha256"),
                                 item.get("nominal_abundance"))
            if (not isinstance(digest, str) or len(digest) != 64
                    or any(c not in "0123456789abcdef" for c in digest)
                    or type(abundance) not in (int, float)
                    or not math.isfinite(abundance)
                    or not 0.15 <= abundance <= 1.0
                    or type(raw) not in (float, int) or not math.isfinite(raw)
                    or type(length) is not int or length <= 0
                    or not -1e-7 <= raw <= length + 1e-7
                    or type(fraction) not in (float, int)
                    or not math.isfinite(fraction)
                    or abs(fraction - raw / length) > 1e-7):
                errors.append(f"{sample}:{name}:invalid_truth_alignment")
                break
            identities[key] = (length, digest, abundance)
            values[key] = raw / length
        else:
            if known is not None and identities != known:
                errors.append(f"{sample}:{name}:inconsistent_truth_panel")
            known = identities if known is None else known
            expected = SCALE * sum(values.values()) / len(values)
            if abs(expected - outcome["score"]) > 1e-5:
                errors.append(f"{sample}:{name}:incorrect_combined_score")
            scores[name] = values
    if (known is None or any(name not in scores for name in results)
            or any(set(table) != set(known) for table in scores.values())):
        return errors
    for key in known:
        strongest = max(scores[name][key] for name in competitors)
        if scores["ivanka"][key] + 1e-7 < minimum_ratio * strongest:
            errors.append(f"{sample}:ivanka_below_90pct_for_{key}")
    return errors

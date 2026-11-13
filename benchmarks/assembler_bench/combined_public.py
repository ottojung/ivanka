"""Combine cohort evidence with explicit within-case score normalization."""
from copy import deepcopy

ID = "current-598-source-attested-combined"
DEDICATED_ID = "current-598-dedicated-combined"


def preview(synthetic, real):
    """Scale final alignment to each case's best measured score, not raw units."""
    result = deepcopy(synthetic)
    samples = []
    for prefix, cohort in (("S", synthetic), ("R", real)):
        for sample in cohort["samples"]:
            row = deepcopy(sample)
            row["alias"] = prefix + "-" + sample["alias"]
            measured = [s for s in row["score"].values() if s is not None]
            top = max(measured) if measured else None
            row["score"] = {k: (v / top if top and v is not None else None)
                            for k, v in row["score"].items()}
            row["family"] = "HXB2 synthetic" if prefix == "S" else "Physical real"
            samples.append(row)
    dedicated = real["id"] == "real198-dedicated-source-live"
    result.update(id=DEDICATED_ID if dedicated else ID,
                  title="Combined · 400 synthetic + 198 real",
                  cohort="combined", hxb2_truth_verified=False,
                  sample_count=len(samples), expected_sample_count=598,
                  samples=samples, families=[], psi={},
                  score_origin="within-case best-measured MiCall score ratio",
                  status_reason=(
                      "Combined 598-case comparison (provisional): alignment "
                      "is normalized to each case's best measured MiCall "
                      "score, because synthetic similarity and physical "
                      "reference-panel points cannot be directly averaged. "
                      "Runtime remains in seconds. Separate cohort gates "
                      "must each pass before qualification."))
    result.pop("cohort_manifest_sha256", None)
    result.pop("hxb2_truth_verified", None)
    result.pop("reference_manifest_sha256", None)
    result.pop("runner_source_sha256", None)
    result.pop("source_truth", None)
    result["cohorts"] = {"synthetic": synthetic["sample_count"],
                         "real": real["sample_count"]}
    result["source_runs"] = [synthetic["id"], real["id"]]
    return result

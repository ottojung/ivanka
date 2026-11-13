"""Combine identically scored MiCall cases without changing measurements."""
from copy import deepcopy
from benchmarks.expanded.gate import SCORE_ORIGIN

ID = "current-598-source-attested-combined"
DEDICATED_ID = "current-598-dedicated-combined"


def preview(synthetic, real):
    """Keep local alignment points and timed seconds intact for all cases."""
    result = deepcopy(synthetic)
    samples = []
    for prefix, cohort in (("S", synthetic), ("R", real)):
        for sample in cohort["samples"]:
            row = deepcopy(sample)
            row["alias"] = prefix + "-" + sample["alias"]
            row["family"] = ("HXB2 synthetic" if prefix == "S"
                             else "Physical real")
            samples.append(row)
    dedicated = real["id"] == "real198-dedicated-source-live"
    result.update(id=DEDICATED_ID if dedicated else ID,
                  title="Combined · 400 synthetic + 198 real",
                  cohort="combined", hxb2_truth_verified=False,
                  sample_count=len(samples), expected_sample_count=598,
                  samples=samples, families=[], psi={},
                  score_origin=SCORE_ORIGIN,
                  status_reason=(
                      "Seven integrated MiCall assemblers compared by "
                      "identical final MAX local-alignment points and "
                      "MiCall runtime, over all 598 cases. Qualification "
                      "requires complete source-attested evidence."))
    for key in ("cohort_manifest_sha256", "hxb2_truth_verified",
                "reference_manifest_sha256", "runner_source_sha256",
                "source_truth"):
        result.pop(key, None)
    result["cohorts"] = {"synthetic": synthetic["sample_count"],
                         "real": real["sample_count"]}
    result["source_runs"] = [synthetic["id"], real["id"]]
    return result

"""Verify retained paired native experiment reports, not integrated qualification."""
import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path

SHA = re.compile(r"[a-f0-9]{64}\Z")
FAMILIES = ("pcr_jackpot", "equal_strains", "coverage_hole", "complex_mixture",
            "minority_30pct", "hcv_hiv_30pct", "clonal", "discordant_pairs")
CASES = {f"{family}-s{i:03d}" for family in FAMILIES for i in range(16)}
BINS = {
    "old": "8569290db7aada4b915feda4648cfd3bcb92a48288cea7918ce36cc9439c3786",
    "new": "ec5eb83546fb4fb212514a3ff54a8fea39e5b016e06ac70f46e2e22a1a931563",
}
ADAPTER = "966c6970939b867521a015f0b4d4e5312558dca366089d54df552afd2c500900"
EMPTY = hashlib.sha256(b"").hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(value):
    return isinstance(value, str) and bool(SHA.fullmatch(value))


def validate(native_bytes, posthoc):
    native = json.loads(native_bytes)
    require(native["not_qualification"] is True and posthoc["not_qualification"] is True,
            "qualification_boundary")
    require(native["adapter_sha256"] == ADAPTER and native["binary_sha256"] == BINS,
            "binary_or_adapter_drift")
    require(set(native["cases"]) == CASES and len(native["cases"]) == len(CASES),
            "case_roster_drift")
    require(native["requested"] == native["attempted"] == 2 * len(CASES)
            == len(native["records"]), "incomplete_native_run")
    require(posthoc["native_report_sha256"] == hashlib.sha256(native_bytes).hexdigest(),
            "posthoc_report_binding")
    require(posthoc["raw_untrimmed_reads"] is True, "input_scope")
    grouped = defaultdict(dict)
    for row in native["records"]:
        case, tag = row["case"], row["arm"]
        require(case in CASES and tag in BINS and tag not in grouped[case],
                "invalid_or_duplicate_arm")
        require(row["binary_sha256"] == BINS[tag], "arm_binary_drift")
        require(row["exit_code"] == 0 and row["stop_reason"] is None
                and digest(row["output_sha256"]) and digest(row["log_sha256"]),
                "arm_not_successful")
        pins = row["input_sha256"]
        require(set(pins) == {"R1", "R2", "seed"} and all(map(digest, pins.values())),
                "input_identity")
        require(row["seeded"] is (pins["seed"] != EMPTY), "adapter_seed_mode")
        require(type(row["peak_rss_kib"]) is int and 0 < row["peak_rss_kib"] <= 512*1024
                and isinstance(row["seconds"], (float, int))
                and math.isfinite(row["seconds"]) and 0 < row["seconds"] <= 31,
                "native_resource_observation")
        grouped[case][tag] = row
    identical, changed = [], []
    for case, pair in sorted(grouped.items()):
        require(set(pair) == set(BINS), "unpaired_case")
        a, b = pair["old"], pair["new"]
        require(a["input_sha256"] == b["input_sha256"] and a["seeded"] == b["seeded"],
                "paired_input_drift")
        (identical if a["output_sha256"] == b["output_sha256"] else changed).append(case)
    require(posthoc["requested_cases"] == len(CASES)
            and posthoc["completed_cases"] == len(posthoc["cases"]), "posthoc_count")
    seen = set()
    for row in posthoc["cases"]:
        case = row["case"]
        require(case in grouped and case not in seen, "posthoc_identity")
        seen.add(case)
        pair = grouped[case]
        require(row["output_sha256"] == {k: v["output_sha256"] for k,v in pair.items()},
                "posthoc_output_drift")
        require(all(row["input_sha256"].get(k) == v for k,v in
                    pair["old"]["input_sha256"].items()) and digest(row["input_sha256"]["truth"]),
                "posthoc_input_drift")
        require(row["outputs_identical"] is (case in identical), "posthoc_equality_drift")
        for truth in row["panel"]:
            for tag in BINS:
                require(0 <= truth["recovered"][tag] <= truth["observed_kmers"]
                        and 0 <= truth["exclusive_recovered"][tag] <= truth["exclusive_kmers"],
                        "invalid_recovery")
    return {"native_arms": len(native["records"]), "case_pairs": len(grouped),
            "identical_pairs": len(identical), "changed_pairs": changed,
            "posthoc_completed": len(seen), "posthoc_not_evaluated": sorted(CASES - seen),
            "not_qualification": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native", type=Path)
    parser.add_argument("posthoc", type=Path)
    a = parser.parse_args()
    print(json.dumps(validate(a.native.read_bytes(), json.loads(a.posthoc.read_bytes())),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""Focused tests for the read-only physical exact-coverage baseline."""
import hashlib
import json

from benchmarks import p2_physical_exact_baseline as baseline

SAMPLES = ["alpha_sample", "beta_sample", "gamma_sample"]


def _report(full, interior, overlap=70):
    def track(values):
        return {
            "zero_fraction": values[0], "mean": values[1],
            "longest_zero_run": values[2], "breadth_ge_1": values[3],
        }
    return {
        "overlap_size": overlap,
        "method": "micall-longest-final-MAX-exact-v2",
        "tracks": {
            baseline.FULL: track(full),
            baseline.INTERIOR: track(interior),
        },
    }


def _write_sidecar(root, sample, tool, report):
    token = hashlib.sha256(sample.encode()).hexdigest()
    path = root / "real" / token / tool / "provenance.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")


def _fixture(tmp_path, ivanka, iva, *, overlap=70):
    sidecars = tmp_path / "sidecars"
    for index, sample in enumerate(SAMPLES):
        if index in ivanka:
            _write_sidecar(sidecars, sample, "ivanka",
                           _report(*ivanka[index], overlap=overlap))
        if index in iva:
            _write_sidecar(sidecars, sample, "iva",
                           _report(*iva[index], overlap=overlap))
    results = tmp_path / "results.jsonl"
    results.write_text(
        "".join(json.dumps({"sample": name}) + "\n" for name in SAMPLES),
        encoding="utf-8")
    return sidecars, results


def test_paired_exact_summary(tmp_path):
    ivanka = {0: ((0.1, 100, 3, 0.9), (0.2, 50, 4, 0.8)),
              1: ((0.3, 200, 5, 0.7), (0.4, 60, 6, 0.6))}
    iva = {0: ((0.0, 150, 0, 1.0), (0.1, 70, 1, 0.9)),
           1: ((0.3, 200, 5, 0.7), (0.4, 60, 6, 0.6))}
    sidecars, results = _fixture(tmp_path, ivanka, iva)
    samples = baseline.canonical_samples(results)
    assert len(samples) == 3
    summary, missing_a, missing_b = baseline.paired_exact(
        sidecars, samples, baseline.FULL, "zero_fraction")
    assert summary.count == 2
    assert abs(summary.mean_diff - 0.05) < 1e-12
    assert summary.first_greater == 1
    assert summary.second_greater == 0
    assert summary.ties == 1
    assert missing_a == [3] and missing_b == [3]
    interior, _, _ = baseline.paired_exact(
        sidecars, samples, baseline.INTERIOR, "mean")
    assert abs(interior.mean_diff + 10.0) < 1e-12


def test_missing_final_max_is_null_not_zero(tmp_path):
    ivanka = {0: ((0.25, 10, 1, 0.75), (0.25, 10, 1, 0.75))}
    iva = {0: ((0.0, 20, 0, 1.0), (0.0, 20, 0, 1.0)),
           1: ((0.5, 5, 2, 0.5), (0.5, 5, 2, 0.5))}
    sidecars, results = _fixture(tmp_path, ivanka, iva)
    samples = baseline.canonical_samples(results)
    summary, missing_a, missing_b = baseline.paired_exact(
        sidecars, samples, baseline.FULL, "zero_fraction")
    assert summary.count == 1
    assert missing_a == [2, 3]
    assert missing_b == [3]
    assert abs(summary.mean_diff - 0.25) < 1e-12
    rows = baseline.per_sample_exact(
        sidecars, samples, baseline.FULL, "zero_fraction")
    assert [row["alias"] for row in rows] == ["R001", "R002", "R003"]
    assert rows[1]["first"] is None
    assert rows[1]["difference"] is None
    assert rows[2]["difference"] is None


def test_unavailable_track_and_wrong_overlap_are_rejected(tmp_path):
    report = _report((0.1, 1, 0, 0.9), (0.1, 1, 0, 0.9))
    sidecars, results = _fixture(tmp_path, {0: ((0.1, 1, 0, 0.9), (0.1, 1, 0, 0.9))},
                                 {0: ((0.0, 2, 0, 1.0), (0.0, 2, 0, 1.0))})
    _write_sidecar(sidecars, SAMPLES[1], "ivanka", report)
    _write_sidecar(sidecars, SAMPLES[1], "iva", report)
    report["tracks"][baseline.FULL] = {"status": "unavailable"}
    _write_sidecar(sidecars, SAMPLES[1], "iva", report)
    samples = baseline.canonical_samples(results)
    summary, missing_a, missing_b = baseline.paired_exact(
        sidecars, samples, baseline.FULL, "zero_fraction")
    assert summary.count == 1 and missing_b == [2, 3]
    _write_sidecar(sidecars, SAMPLES[0], "iva",
                   _report((0, 1, 0, 1), (0, 1, 0, 1), overlap=31))
    try:
        baseline.paired_exact(sidecars, samples, baseline.FULL, "mean")
    except ValueError:
        pass
    else:
        raise AssertionError("wrong overlap size must fail closed")


def test_frozen_v6_sidecar_layout_is_read(tmp_path):
    sidecars, results = _fixture(
        tmp_path,
        {0: ((0.1, 1, 0, 0.9), (0.1, 1, 0, 0.9))},
        {0: ((0.0, 2, 0, 1.0), (0.0, 2, 0, 1.0))})
    token = hashlib.sha256(SAMPLES[0].encode()).hexdigest()
    for tool, depth in (("ivanka", 1), ("iva", 3)):
        frozen = sidecars / "real" / tool / token / tool / "provenance.json"
        frozen.parent.mkdir(parents=True, exist_ok=True)
        frozen.write_text(json.dumps(_report((0.0, depth, 0, 1.0),
                                              (0.0, depth, 0, 1.0))),
                          encoding="utf-8")
    summary, _, _ = baseline.paired_exact(
        sidecars, baseline.canonical_samples(results), baseline.FULL, "mean")
    assert summary.count == 1 and summary.mean_diff == -2.0


def test_paired_diagnostics_preserves_nulls(tmp_path):
    runs = {
        "runs": [{
            "cohort": "real",
            "samples": [
                {"diagnostics": {"ivanka": {"average_concordance": 0.9},
                                 "iva": {"average_concordance": 0.8}}},
                {"diagnostics": {"ivanka": {"average_concordance": 0.7},
                                 "iva": {}}},
            ],
        }],
    }
    path = tmp_path / "runs.json"
    path.write_text(json.dumps(runs), encoding="utf-8")
    summary = baseline.paired_diagnostics(path, "real", "average_concordance")
    assert summary.count == 1 and abs(summary.mean_diff - 0.1) < 1e-12


def test_recompute_reports_hashes_and_witness_order(tmp_path):
    ivanka = {0: ((0.1, 10, 0, 0.9), (0.2, 5, 1, 0.8))}
    iva = {0: ((0.0, 20, 0, 1.0), (0.1, 6, 0, 0.9))}
    sidecars, results = _fixture(tmp_path, ivanka, iva)
    runs = {"runs": [{"cohort": "real", "samples": [
        {"diagnostics": {"ivanka": {"average_concordance": 0.9},
                         "iva": {"average_concordance": 0.8}}}]}]}
    runs_path = tmp_path / "runs.json"
    runs_path.write_text(json.dumps(runs), encoding="utf-8")
    witness = tmp_path / "witness.json"
    witness.write_text(json.dumps({"samples": {name: [] for name in SAMPLES}}),
                       encoding="utf-8")
    summary = baseline.recompute(runs_path, sidecars, results, witness)
    assert summary["sources"]["runs_sha256"] == baseline.sha256_file(runs_path)
    assert summary["sources"]["canonical_sample_count"] == 3
    assert summary["sources"]["witness_order_matches"] is True
    assert summary["exact"][f"{baseline.FULL}.zero_fraction"]["paired_cases"] == 1
    assert abs(summary["diagnostics"]["average_concordance"]["mean_difference"] - 0.1) < 1e-12

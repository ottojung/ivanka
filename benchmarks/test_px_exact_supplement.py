"""Tests for versioned, hash-bound supplemental exact-coverage joining."""
import hashlib
import json
from pathlib import Path

from assembler_bench import px_exact_supplement as sup
from assembler_bench.metric_catalog_exact import catalog


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _setup(tmp):
    tmp = Path(tmp)
    (tmp / "receipts").mkdir(exist_ok=True)
    (tmp / "diagnostics").mkdir(exist_ok=True)
    (tmp / "supplements").mkdir(exist_ok=True)
    name = "skesa-physical-PX-R037"
    receipt = {
        "schema": "ivanka.px.case.receipt.v1", "tool_id": "skesa",
        "cohort": "physical", "alias": "PX-R037", "outcome": "success",
        "image_sha256": "e" * 64, "output_sha256": "a" * 64,
        "input_sha256": {"R1": "b" * 64, "R2": "c" * 64},
    }
    rbytes = (json.dumps(receipt, sort_keys=True) + "\n").encode()
    (tmp / "receipts" / (name + ".json")).write_bytes(rbytes)
    (tmp / "receipts" / "index.json").write_text(json.dumps({
        "schema": "ivanka.px.case.receipt-index.v1",
        "entries": {name: _sha(rbytes)}}))
    diagnostics = {
        "schema": "ivanka.px.diagnostics.v3", "tool_id": "skesa",
        "image_sha256": "e" * 64, "output_sha256": "a" * 64,
        "metrics": {"exact_coverage": {
            "status": "unavailable",
            "unavailable_reason": "exact coverage module unavailable: No module named 'micall'"}},
    }
    dbytes = (json.dumps(diagnostics, sort_keys=True) + "\n").encode()
    (tmp / "diagnostics" / (name + ".json")).write_bytes(dbytes)
    Path(str(tmp / "diagnostics" / (name + ".json")) + ".sha256").write_text(
        _sha(dbytes) + "\n")
    coverage = dict(diagnostics["metrics"]["exact_coverage"])
    csv_bytes = b"contig,position,exact_coverage\n"
    values = {key: 1 for key in catalog()}
    supplement = {
        "schema": sup.SCHEMA, "schema_version": sup.SCHEMA_VERSION,
        "generator": {"name": sup.GENERATOR_NAME, "version": sup.GENERATOR_VERSION,
                      "method": sup.METHOD, "overlap_size": sup.OVERLAP_SIZE},
        "case": {"alias": "PX-R037", "cohort": "physical", "tool_id": "skesa",
                 "receipt_sha256": _sha(rbytes)},
        "bindings": {"image_sha256": "e" * 64, "final_conseq_sha256": "a" * 64,
                     "fastq_sha256": ["b" * 64, "c" * 64],
                     "module_sha256": sup.PINNED_MODULE_SHA256,
                     "overlap_size": sup.OVERLAP_SIZE, "method": sup.METHOD},
        "diagnostics_binding": {"path": "diagnostics/" + name + ".json",
                                "record_sha256": _sha(dbytes),
                                "original_exact_status": "unavailable",
                                "original_unavailable_reason": "unavailable"},
        "exact_coverage_sha256": _sha(csv_bytes),
        "values": values,
    }
    return tmp, name, receipt, diagnostics, coverage, supplement, csv_bytes


def _write_supplement(tmp, name, supplement, csv_bytes):
    path = tmp / "supplements" / (name + ".json")
    path.write_bytes(sup.json_bytes(supplement))
    Path(str(path) + ".sha256").write_text(_sha(path.read_bytes()) + "\n")
    (tmp / "supplements" / (name + sup.CSV_SUFFIX)).write_bytes(csv_bytes)
    return path


def test_no_supplement_keeps_original_unavailable(tmp_path):
    tmp, name, receipt, diagnostics, coverage, _, _ = _setup(tmp_path)
    assert sup.join_at_publication(coverage, tmp, name, receipt, diagnostics) == coverage


def test_verified_supplement_joins_extracted(tmp_path):
    tmp, name, receipt, diagnostics, coverage, supplement, csv = _setup(tmp_path)
    _write_supplement(tmp, name, supplement, csv)
    joined = sup.join_at_publication(coverage, tmp, name, receipt, diagnostics)
    assert joined["status"] == "extracted" and joined["unavailable_reason"] is None
    assert joined["values"] == supplement["values"]
    assert set(joined["evidence"]) == sup.EVIDENCE_KEYS
    assert joined["evidence"]["implementation_sha256"] == sup.PINNED_MODULE_SHA256
    assert coverage["status"] == "unavailable"  # immutable record untouched


def test_binding_mismatch_blocks_publication(tmp_path):
    tmp, name, receipt, diagnostics, coverage, supplement, csv = _setup(tmp_path)
    supplement["bindings"]["module_sha256"] = "0" * 64
    _write_supplement(tmp, name, supplement, csv)
    try:
        sup.join_at_publication(coverage, tmp, name, receipt, diagnostics)
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched module hash must fail closed")


def test_supplement_sidecar_mismatch_blocks_publication(tmp_path):
    tmp, name, receipt, diagnostics, coverage, supplement, csv = _setup(tmp_path)
    path = _write_supplement(tmp, name, supplement, csv)
    Path(str(path) + ".sha256").write_text("1" * 64 + "\n")
    try:
        sup.join_at_publication(coverage, tmp, name, receipt, diagnostics)
    except ValueError:
        pass
    else:
        raise AssertionError("supplement sidecar mismatch must fail closed")


def test_diagnostic_sidecar_mismatch_blocks_publication(tmp_path):
    tmp, name, receipt, diagnostics, coverage, supplement, csv = _setup(tmp_path)
    _write_supplement(tmp, name, supplement, csv)
    Path(str(tmp / "diagnostics" / (name + ".json")) + ".sha256").write_text(
        "2" * 64 + "\n")
    try:
        sup.join_at_publication(coverage, tmp, name, receipt, diagnostics)
    except ValueError:
        pass
    else:
        raise AssertionError("diagnostic sidecar mismatch must fail closed")


def test_csv_digest_mismatch_blocks_publication(tmp_path):
    tmp, name, receipt, diagnostics, coverage, supplement, csv = _setup(tmp_path)
    _write_supplement(tmp, name, supplement, csv + b"tampered\n")
    try:
        sup.join_at_publication(coverage, tmp, name, receipt, diagnostics)
    except ValueError:
        pass
    else:
        raise AssertionError("CSV digest mismatch must fail closed")


def test_generator_identity_enforced(tmp_path):
    tmp, name, receipt, diagnostics, coverage, supplement, csv = _setup(tmp_path)
    supplement["generator"]["version"] = "9.9.9"
    _write_supplement(tmp, name, supplement, csv)
    try:
        sup.join_at_publication(coverage, tmp, name, receipt, diagnostics)
    except ValueError:
        pass
    else:
        raise AssertionError("generator identity must be enforced")


def test_unexpected_metric_keys_blocked(tmp_path):
    tmp, name, receipt, diagnostics, coverage, supplement, csv = _setup(tmp_path)
    supplement["values"]["arbitrary_key"] = 1
    _write_supplement(tmp, name, supplement, csv)
    try:
        sup.join_at_publication(coverage, tmp, name, receipt, diagnostics)
    except ValueError:
        pass
    else:
        raise AssertionError("arbitrary metric keys must be blocked")


def test_clinical_string_in_supplement_blocked(tmp_path):
    tmp, name, receipt, diagnostics, coverage, supplement, csv = _setup(tmp_path)
    supplement["case"]["clinical_sample"] = "63899A-V3-2-V3LOOP_S14"
    _write_supplement(tmp, name, supplement, csv)
    try:
        sup.join_at_publication(coverage, tmp, name, receipt, diagnostics)
    except ValueError:
        pass
    else:
        raise AssertionError("clinical identity in supplement must fail closed")


def test_extracted_record_never_overwritten(tmp_path):
    tmp, name, receipt, diagnostics, _, supplement, csv = _setup(tmp_path)
    _write_supplement(tmp, name, supplement, csv)
    extracted = {"status": "extracted", "unavailable_reason": None,
                 "values": {"already": 1}}
    assert sup.join_at_publication(extracted, tmp, name, receipt, diagnostics) is extracted


def test_public_privacy_guard(tmp_path):
    assert sup.assert_public_private({"alias": "R037", "values": {}}) == {
        "alias": "R037", "values": {}}
    for bad in ({"sample": "63899A-V3-2-V3LOOP_S14"},
                {"sequence": "ACGT" * 20}):
        try:
            sup.assert_public_private(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("clinical identity must not appear in public JSON")

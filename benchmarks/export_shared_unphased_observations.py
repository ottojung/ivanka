"""Export provenance-correct SHARED, UNPHASED local block observations.

Opt-in, read-only postprocess. It never assigns one original fragment to
competing haplotypes, never imputes missing inserts, never infers full-length
phase, never writes into MiCall/FASTQ source directories, and never modifies
final MiCall MAX, 198 acceptance, IVA cache, or reference panels.

Consumers: the authenticated verifier recomputes observations from hash-pinned
original MiCall/FASTQ sources. Parsing JSON booleans alone is NEVER sufficient
for empirical claims; use verify_observation_export / authenticated consume.
"""
import argparse
import csv
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

from attest_remap_fastq_provenance import attest, digest
from shared_block_consensus_candidate import (
    _pair_signature, _strict_pair, audit_remap, canonical_base,
)
from shared_locus_remap_coverage import group_loci, sam_observations

SCHEMA = "ivanka.shared_unphased_observation_export.v1"
VERIFY_SCHEMA = "ivanka.shared_unphased_observation_verification.v1"
BASES = "ACGT"


class ObservationExportError(ValueError):
    """Fail-closed export/verification error."""


def _sha256(path):
    return digest(path)


def _exact_final_mask(final_conseq_csv, region, mask_start, mask_end):
    with Path(final_conseq_csv).open() as fh:
        rows = [r for r in csv.DictReader(fh)
                if r["region"] == region and r["q-cutoff"] == "15"
                and r["consensus-percent-cutoff"] == "MAX"]
    if len(rows) != 1:
        raise ObservationExportError("Expected exactly one Q15 MAX final region")
    seq = rows[0]["sequence"]
    if not (0 <= mask_start < mask_end <= len(seq)):
        raise ObservationExportError("Mask interval outside final region")
    if seq[mask_start:mask_end] != "x" * (mask_end - mask_start):
        raise ObservationExportError("Selected interval must be an exact lowercase-x mask")
    return seq


def _site_spectrum(allele, loci, sam_rows, minimum_quality):
    calls = [defaultdict(set) for _ in allele]
    groups = defaultdict(list)
    for row in sam_rows:
        name = row.get("qname")
        if name:
            groups[name].append(row)
    strict_evaluated = 0
    for qname, rows in groups.items():
        if not _strict_pair(rows) or rows[0]["rname"] not in loci:
            continue
        try:
            _pair_signature(rows)
        except ValueError:
            continue
        strict_evaluated += 1
        for row in rows:
            for site, base, _, expected in sam_observations(
                    row, loci[row["rname"]], minimum_quality):
                try:
                    cb = canonical_base(base, expected, allele[site])
                except ValueError:
                    cb = None
                calls[site][qname].add(cb)

    per_site = []
    for site, qmap in enumerate(calls):
        counts = {"A": 0, "C": 0, "G": 0, "T": 0,
                  "conflict_or_non_acgt_original_pair_ids": 0}
        for bases in qmap.values():
            value = next(iter(bases)) if len(bases) == 1 else None
            if isinstance(value, str) and value in BASES:
                counts[value] += 1
            else:
                counts["conflict_or_non_acgt_original_pair_ids"] += 1
        shared_base = allele[site]
        per_site.append({
            "site_zero_based_in_mask": site,
            "shared_reference_expected_base": shared_base,
            "q15_original_pair_base_counts": {b: counts[b] for b in BASES},
            "q15_conflict_or_non_acgt_original_pair_ids":
                counts["conflict_or_non_acgt_original_pair_ids"],
            "q15_shared_expected_base_original_pair_ids": counts[shared_base],
            "q15_alternative_base_original_pair_ids": sum(
                counts[b] for b in BASES if b != shared_base),
            "q15_original_pair_ids_with_any_call": sum(
                counts[b] for b in BASES) + counts[
                    "conflict_or_non_acgt_original_pair_ids"],
            "pooled_across_selected_hypotheses": True,
            "assigned_to_single_haplotype": False,
        })

    complete_alleles = defaultdict(int)
    for qname in {n for qmap in calls for n in qmap}:
        values = []
        for site in range(len(allele)):
            bases = calls[site].get(qname)
            value = next(iter(bases)) if bases and len(bases) == 1 else None
            values.append(value)
        if all(isinstance(v, str) and v in BASES for v in values):
            complete_alleles["".join(values)] += 1
    complete_block_pairs = sum(complete_alleles.values())
    complete_shared_pairs = complete_alleles.get(allele, 0)
    return {
        "strict_original_read_pair_ids_evaluated": strict_evaluated,
        "per_site_q15_observed_allele_spectrum": per_site,
        "complete_block_original_pair_observations": {
            "original_pair_ids_observing_every_mask_site_once": complete_block_pairs,
            "shared_reference_allele_original_pair_ids": complete_shared_pairs,
            "non_shared_complete_local_allele_original_pair_ids":
                complete_block_pairs - complete_shared_pairs,
            "complete_local_allele_original_pair_id_counts": dict(
                sorted(complete_alleles.items())),
            "local_complete_block_only_not_full_length_phase": True,
            "counts_not_independent_physical_molecules": True,
        },
    }


def export_observations(final_conseq_csv, remap_conseq_csv, remap_sam_csv,
                        *, region, references, mask_start, mask_end,
                        anchor=31, minimum_quality=15,
                        fastq_r1=None, fastq_r2=None, label=None):
    if minimum_quality < 15:
        raise ObservationExportError("Refusing evidence below Q15")
    if (not isinstance(references, (list, tuple)) or len(references) < 2
            or len(set(references)) != len(references)
            or any(not isinstance(r, str) or not r for r in references)):
        raise ObservationExportError("Need >=2 distinct selected references")
    final_seq = _exact_final_mask(final_conseq_csv, region, mask_start, mask_end)
    with Path(remap_conseq_csv).open() as fh:
        seeds = {r["region"]: r["sequence"].upper() for r in csv.DictReader(fh)}
    try:
        selected_refs = {name: seeds[name] for name in references}
    except KeyError as exc:
        raise ObservationExportError(f"Missing remap reference {exc}") from exc
    masked = SimpleNamespace(sequence=final_seq, start=mask_start, end=mask_end)
    allele, loci = group_loci(masked, selected_refs, anchor=anchor)
    with Path(remap_sam_csv).open() as fh:
        sam = list(csv.DictReader(fh))
    spectrum = _site_spectrum(allele, loci, sam, minimum_quality)
    raw_attestation = None
    if fastq_r1 or fastq_r2:
        if not (fastq_r1 and fastq_r2):
            raise ObservationExportError("Both original FASTQ mates are required")
        raw_attestation = attest(remap_sam_csv, fastq_r1, fastq_r2)
        if raw_attestation["source_sha256"]["original_remap_csv"] != _sha256(remap_sam_csv):
            raise ObservationExportError("FASTQ remap hash mismatch")
    audit = audit_remap(masked, selected_refs, sam, minimum_quality, 1)
    if len(audit["positions"]) != len(allele):
        raise ObservationExportError("Audit length mismatch")
    return {
        "schema_version": SCHEMA,
        "artifact_type": "shared_unphased_observation_export",
        "label": label,
        "region": region,
        "mask_interval_zero_based_half_open": {
            "start": mask_start, "end": mask_end,
            "length": mask_end - mask_start},
        "shared_reference_membership": {
            "selected_reference_names": list(references),
            "reference_count": len(references),
            "all_selected_references_share_exact_flanked_allele": True,
            "shared_block_length": len(allele),
            "shared_block_sha256": hashlib.sha256(allele.encode()).hexdigest(),
        },
        "source_checksums_sha256": {
            "final_conseq_csv": _sha256(final_conseq_csv),
            "remap_conseq_csv": _sha256(remap_conseq_csv),
            "remap_sam_csv": _sha256(remap_sam_csv),
            **({"original_fastq_r1": raw_attestation["source_sha256"]["original_fastq_r1"],
                "original_fastq_r2": raw_attestation["source_sha256"]["original_fastq_r2"]}
               if raw_attestation else {}),
        },
        "source_paths": {
            "final_conseq_csv": str(Path(final_conseq_csv).resolve()),
            "remap_conseq_csv": str(Path(remap_conseq_csv).resolve()),
            "remap_sam_csv": str(Path(remap_sam_csv).resolve()),
            **({"original_fastq_r1": str(Path(fastq_r1).resolve()),
                "original_fastq_r2": str(Path(fastq_r2).resolve())}
               if raw_attestation else {}),
        },
        "original_fastq_mate_provenance": ({
            "attested": True,
            "empirical_claim_requires_strict_fastq_mate_provenance": True,
            "raw_attestation": raw_attestation,
        } if raw_attestation else {
            "attested": False,
            "reason": "no_raw_fastq_mates_provided",
            "empirical_claim_requires_strict_fastq_mate_provenance": True,
        }),
        "minimum_phred_quality": minimum_quality,
        "anchor_bp": anchor,
        **spectrum,
        "phase_status": "unidentified",
        "unphased": True,
        "full_length_haplotype_phase_inferred": False,
        "independent_physical_molecules_assigned": False,
        "haplotype_specific_depth_assigned": False,
        "original_fragment_assigned_to_competing_haplotypes": False,
        "missing_insert_bases_imputed": False,
        "raw_qnames_included": False,
        "modifies_micall_consensus": False,
        "modifies_final_max_sequence": False,
        "affects_198_acceptance": False,
        "safe_for_final_max_overwrite": False,
        "interpretation": (
            "Shared, unphased local observations from original strict read pairs. "
            "Per-site spectra are pooled across selected reference hypotheses; "
            "counts are original pair IDs, not independent DNA molecules. Minority "
            "alleles are preserved as observed counts and never assigned to a "
            "competing haplotype. Missing/unsequenced inserts are not imputed. "
            "This artifact must not overwrite final MiCall MAX or 198 acceptance."),
    }


def _canonical_json(obj):
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def _assert_safety_metadata(report):
    if report.get("schema_version") != SCHEMA:
        raise ObservationExportError(f"Unsupported schema: {report.get('schema_version')}")
    required_false = (
        "modifies_micall_consensus", "modifies_final_max_sequence",
        "safe_for_final_max_overwrite", "affects_198_acceptance",
        "full_length_haplotype_phase_inferred",
        "original_fragment_assigned_to_competing_haplotypes",
        "haplotype_specific_depth_assigned",
        "independent_physical_molecules_assigned", "missing_insert_bases_imputed",
        "raw_qnames_included",
    )
    if any(report.get(field) is not False for field in required_false):
        raise ObservationExportError("Unsafe or incomplete export safety metadata")
    if (report.get("artifact_type") != "shared_unphased_observation_export"
            or report.get("unphased") is not True
            or report.get("phase_status") != "unidentified"):
        raise ObservationExportError("Export must be explicitly unphased")
    if type(report.get("minimum_phred_quality")) is not int or report["minimum_phred_quality"] < 15:
        raise ObservationExportError("Export quality below Q15")


def _bind_independent_sources(report, artifact_dir, screen_ledger, sample,
                              expected_screen_sha256):
    """Bind an otherwise self-describing report to trusted caller inputs.

    The caller selects both the original MiCall directory and the separately
    attested discovery/direct-link cohort ledger. JSON cannot select its own
    trusted source root, sample, mask or expected source hashes.
    """
    root = Path(artifact_dir).resolve(strict=True)
    if not root.is_dir():
        raise ObservationExportError("Expected original MiCall result directory")
    paths = report["source_paths"]
    expected = {"final_conseq_csv": root / "conseq.csv",
                "remap_conseq_csv": root / "remap_conseq.csv",
                "remap_sam_csv": root / "scratch" / "remap.csv"}
    for name, path in expected.items():
        if (not path.is_file() or
                Path(paths.get(name, "")).resolve() != path.resolve()):
            raise ObservationExportError(f"Independent source path mismatch: {name}")
    if not isinstance(sample, str) or not sample:
        raise ObservationExportError("Missing independent sample identity")
    if (not isinstance(expected_screen_sha256, str)
            or len(expected_screen_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_screen_sha256)
            or _sha256(screen_ledger) != expected_screen_sha256):
        raise ObservationExportError("Independent cohort screen SHA256 is not externally pinned")
    ledger = json.loads(Path(screen_ledger).read_text())
    if ledger.get("schema_version") != "ivanka.shared_mask_direct_cohort_screen.v1":
        raise ObservationExportError("Expected caller-supplied direct-link cohort ledger")
    mask = report["mask_interval_zero_based_half_open"]
    refs = report["shared_reference_membership"]["selected_reference_names"]
    chosen = [item for item in ledger.get("records", [])
              if item.get("sample") == sample
              and item.get("region") == report["region"]
              and item.get("mask_start") == mask["start"]
              and item.get("mask_end") == mask["end"]
              and item.get("selected_reference_names") == refs]
    if len(chosen) != 1:
        raise ObservationExportError("Independent ledger does not select this exact mask")
    previous = chosen[0]["source_sha256"]
    for name in expected:
        key = "original_remap_sam_csv" if name == "remap_sam_csv" else name
        if (previous.get(key) != report["source_checksums_sha256"].get(name)
                or previous[key] != _sha256(expected[name])):
            raise ObservationExportError(f"Independent source hash mismatch: {name}")
    return _sha256(screen_ledger)


def verify_observation_export(report, *, require_fastq=False,
                              artifact_dir=None, screen_ledger=None, sample=None,
                              expected_screen_sha256=None,
                              original_fastq_r1=None, original_fastq_r2=None):
    _assert_safety_metadata(report)
    binding = (artifact_dir, screen_ledger, sample, expected_screen_sha256)
    if any(v is not None for v in binding) and not all(
            v is not None for v in binding):
        raise ObservationExportError("Require artifact directory, screen ledger and sample together")
    independent_ledger_sha = (
        _bind_independent_sources(report, artifact_dir, screen_ledger, sample,
                                  expected_screen_sha256)
        if artifact_dir is not None else None)
    if (original_fastq_r1 is None) != (original_fastq_r2 is None):
        raise ObservationExportError("Both external FASTQ mate paths required")
    externally_bound_raw = False
    if original_fastq_r1 is not None:
        paths = report.get("source_paths") or {}
        if not all(
            Path(paths.get(name, "")).resolve() == Path(path).resolve(strict=True)
            for name, path in (("original_fastq_r1", original_fastq_r1),
                               ("original_fastq_r2", original_fastq_r2))):
            raise ObservationExportError("External FASTQ source paths disagree with report")
        externally_bound_raw = True
    paths = report.get("source_paths") or {}
    sums = report.get("source_checksums_sha256") or {}
    for key in ("final_conseq_csv", "remap_conseq_csv", "remap_sam_csv"):
        path = paths.get(key)
        expected = sums.get(key)
        if not path or not expected or not Path(path).is_file():
            raise ObservationExportError(f"Missing source for {key}")
        actual = _sha256(path)
        if actual != expected:
            raise ObservationExportError(f"Source checksum mismatch for {key}")
    refs = report.get("shared_reference_membership", {}).get("selected_reference_names")
    mask = report.get("mask_interval_zero_based_half_open") or {}
    raw = report.get("original_fastq_mate_provenance") or {}
    fastq_claimed = raw.get("attested") is True or raw.get("all_remap_sequences_and_quality_from_raw_mates") is True
    expected_raw = raw.get("raw_attestation") if isinstance(raw.get("raw_attestation"), dict) else (raw if raw.get("all_remap_sequences_and_quality_from_raw_mates") is True else None)
    if require_fastq and not fastq_claimed:
        raise ObservationExportError("Empirical use requires authenticated FASTQ provenance")
    if fastq_claimed:
        r1, r2 = paths.get("original_fastq_r1"), paths.get("original_fastq_r2")
        if not r1 or not r2 or expected_raw is None:
            raise ObservationExportError("FASTQ provenance missing mate paths or attestation")
        for key, path in (("original_fastq_r1", r1), ("original_fastq_r2", r2)):
            expected = sums.get(key)
            if not expected or _sha256(path) != expected:
                raise ObservationExportError(f"FASTQ checksum mismatch for {key}")
        reattested = attest(paths["remap_sam_csv"], r1, r2)
        if reattested != expected_raw:
            raise ObservationExportError("FASTQ provenance does not reattest identically")
    recomputed = export_observations(
        paths["final_conseq_csv"], paths["remap_conseq_csv"], paths["remap_sam_csv"],
        region=report["region"], references=refs,
        mask_start=mask["start"], mask_end=mask["end"],
        anchor=report.get("anchor_bp", 31),
        minimum_quality=report["minimum_phred_quality"],
        fastq_r1=paths.get("original_fastq_r1") if fastq_claimed else None,
        fastq_r2=paths.get("original_fastq_r2") if fastq_claimed else None,
        label=report.get("label"))
    if _canonical_json(recomputed) != _canonical_json(report):
        raise ObservationExportError("Export content disagrees with deterministic recomputation")
    return {
        "schema_version": VERIFY_SCHEMA,
        "verification": (
            "passed_source_checksums_deterministic_recomputation_and_raw_fastq_mate_provenance"
            if fastq_claimed else
            "passed_source_checksums_and_deterministic_recomputation"),
        "export_schema_version": SCHEMA,
        "label": report.get("label"),
        "region": report["region"],
        "mask_interval_zero_based_half_open": mask,
        "raw_fastq_mate_provenance_authenticated": fastq_claimed,
        "strict_original_read_pair_ids_evaluated":
            report["strict_original_read_pair_ids_evaluated"],
        "modifies_micall_consensus": False,
        "modifies_final_max_sequence": False,
        "affects_198_acceptance": False,
        "phase_status": "unidentified",
        "haplotype_specific_depth_assigned": False,
        "independent_physical_molecules_assigned": False,
        "consumer_mode": "authenticated_recomputed",
        "source_binding": ("caller_pinned_original_micall_and_cohort_screen"
                           if independent_ledger_sha is not None
                           else "self_declared_source_paths_not_trusted"),
        "independent_cohort_screen_sha256": independent_ledger_sha,
        "externally_bound_original_fastq_mates": externally_bound_raw,
        "empirical_use_permitted": (
            independent_ledger_sha is not None and externally_bound_raw and
            fastq_claimed and require_fastq),
    }


def consume_observations(path, *, authenticated=True, require_fastq=False,
                         artifact_dir=None, screen_ledger=None, sample=None,
                         expected_screen_sha256=None,
                         original_fastq_r1=None, original_fastq_r2=None):
    report = json.loads(Path(path).read_text())
    _assert_safety_metadata(report)
    if not authenticated:
        report = dict(report)
        report["consumer_mode"] = "untrusted_parse_diagnostic_only"
        report["empirical_use_permitted"] = False
        return report
    status = verify_observation_export(
        report, require_fastq=require_fastq, artifact_dir=artifact_dir,
        screen_ledger=screen_ledger, sample=sample,
        expected_screen_sha256=expected_screen_sha256,
        original_fastq_r1=original_fastq_r1,
        original_fastq_r2=original_fastq_r2)
    report = dict(report)
    report["verification_status"] = status
    report["consumer_mode"] = status["consumer_mode"]
    return report


def _safe_write(report, output, forbidden_roots):
    out = Path(output).resolve()
    encoded = _canonical_json(report)
    for root in forbidden_roots:
        r = Path(root).resolve()
        if out == r or r in out.parents:
            raise ObservationExportError(f"Refusing to write inside source directory {r}")
    if out.exists():
        if not out.is_file() or out.read_text() != encoded:
            raise ObservationExportError("Refusing to overwrite different existing file")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(encoded)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export", help="Export unphased observations")
    ex.add_argument("final_conseq_csv", type=Path)
    ex.add_argument("remap_conseq_csv", type=Path)
    ex.add_argument("remap_sam_csv", type=Path)
    ex.add_argument("--region", required=True)
    ex.add_argument("--reference", action="append", required=True)
    ex.add_argument("--mask-start", type=int, required=True)
    ex.add_argument("--mask-end", type=int, required=True)
    ex.add_argument("--anchor", type=int, default=31)
    ex.add_argument("--min-phred", type=int, default=15)
    ex.add_argument("--original-fastq-r1", type=Path)
    ex.add_argument("--original-fastq-r2", type=Path)
    ex.add_argument("--label")
    ex.add_argument("--output", type=Path, required=True)
    ex.add_argument("--forbidden-root", action="append", default=[], type=Path)
    vf = sub.add_parser("verify", help="Fail-closed authenticated verification")
    vf.add_argument("observation_json", type=Path)
    vf.add_argument("--require-fastq", action="store_true")
    vf.add_argument("--artifact-dir", type=Path)
    vf.add_argument("--screen-ledger", type=Path)
    vf.add_argument("--screen-sha256")
    vf.add_argument("--sample")
    vf.add_argument("--original-fastq-r1", type=Path)
    vf.add_argument("--original-fastq-r2", type=Path)
    vf.add_argument("--status-output", type=Path)
    args = p.parse_args(argv)
    try:
        if args.cmd == "export":
            report = export_observations(
                args.final_conseq_csv, args.remap_conseq_csv, args.remap_sam_csv,
                region=args.region, references=args.reference,
                mask_start=args.mask_start, mask_end=args.mask_end,
                anchor=args.anchor, minimum_quality=args.min_phred,
                fastq_r1=args.original_fastq_r1, fastq_r2=args.original_fastq_r2,
                label=args.label)
            forbidden = [args.final_conseq_csv.parent, args.remap_conseq_csv.parent,
                         args.remap_sam_csv.parent,
                         *( [args.original_fastq_r1.parent, args.original_fastq_r2.parent]
                            if args.original_fastq_r1 and args.original_fastq_r2 else []),
                         *args.forbidden_root]
            _safe_write(report, args.output, forbidden)
            status = verify_observation_export(report, require_fastq=bool(args.original_fastq_r1))
            print(json.dumps(status, sort_keys=True))
        else:
            report = json.loads(args.observation_json.read_text())
            status = verify_observation_export(
                report, require_fastq=args.require_fastq,
                artifact_dir=args.artifact_dir, screen_ledger=args.screen_ledger,
                sample=args.sample, expected_screen_sha256=args.screen_sha256,
                original_fastq_r1=args.original_fastq_r1,
                original_fastq_r2=args.original_fastq_r2)
            encoded = _canonical_json(status)
            if args.status_output:
                dest = args.status_output.resolve()
                src = Path(args.observation_json).resolve()
                protected = [src.parent, src, *(Path(v).resolve().parent for v in (report.get("source_paths") or {}).values() if v)]
                for root in protected:
                    if dest == root or root in dest.parents:
                        raise ObservationExportError("Cannot write status inside source directories")
                if dest.exists():
                    if not dest.is_file() or dest.read_text() != encoded:
                        raise ObservationExportError("Refusing to overwrite different status")
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, "w") as f:
                        f.write(encoded)
            else:
                print(encoded, end="")
    except (ObservationExportError, ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()

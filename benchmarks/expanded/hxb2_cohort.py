"""Create or verify an HXB2-anchored 25-family viral benchmark cohort."""
import argparse
import hashlib
import json
from pathlib import Path

from .hxb2_truth import haplotypes, validate, references
from .synthetic import FAMILIES, generate_cohort, fingerprint


def verify_cohort(directory, *, expected=400):
    directory = Path(directory)
    manifest = json.loads((directory / "cohort.json").read_text())
    schema = manifest.get("schema")
    if (schema not in ("ivanka.expanded.cohort.hxb2.v1",
                      "ivanka.expanded.cohort.hxb2.v2")
            or len(manifest["cases"]) != expected
            or manifest.get("samples") != expected
            or set(manifest["families"]) != set(FAMILIES)
            or len({x["id"] for x in manifest["cases"]}) != expected):
        raise ValueError("wrong HXB2 synthetic cohort schema or count")
    if schema == "ivanka.expanded.cohort.hxb2.v2":
        from .hxb2_lowdepth_v2 import verify_metadata
        verify_metadata(directory, manifest)
    import gzip
    for row in manifest["cases"]:
        case = directory / row["id"]
        if not validate(case):
            raise ValueError("invalid HXB2 truth")
        reads = []
        for mate in (1, 2):
            with gzip.open(case / f"reads/R{mate}.fastq.gz", "rt") as file:
                headers = [line.strip() for i, line in enumerate(file)
                           if i % 4 == 0]
            if any(not header.startswith("@synthetic:")
                   or not header.endswith(f" {mate}:N:0:1")
                   for header in headers):
                raise ValueError("FASTQ headers incompatible with actual MiCall")
            reads.append(headers)
        if len(reads[0]) != len(reads[1]) or any(
                a.split()[0] != b.split()[0]
                for a, b in zip(*reads)):
            raise ValueError("paired-read identity mismatch")
        recorded = json.loads((case / "manifest.json").read_text())
        if (recorded["sha256"] != row["sha256"]
                or recorded.get("pairs") != len(reads[0])
                or recorded.get("read_length") != 150
                or sum(recorded.get("sampled_haplotype_pairs", []))
                   != recorded["pairs"]):
            raise ValueError("case provenance does not match cohort")
    return fingerprint(directory / "cohort.json")


def attestation(directory, *, expected=400):
    """Provide a deterministic digest of a fully replay-validated cohort."""
    digest = verify_cohort(directory, expected=expected)
    panel = fingerprint(Path(__file__).parent / "references/manifest.json")
    cohort = json.loads((Path(directory) / "cohort.json").read_text())
    variant = ("v2" if cohort["schema"].endswith(".v2") else "v1")
    material = (digest + panel + "ivanka.expanded.hxb2_ancestry." + variant).encode()
    return {
        "schema": "ivanka.hxb2_truth_validation." + variant,
        "valid": True, "samples_validated": expected,
        "cohort_sha256": digest,
        "reference_manifest_sha256": panel,
        "verification_sha256": hashlib.sha256(material).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--seeds", type=int, default=16)
    parser.add_argument("--pairs", type=int, default=900)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--derive-low-depth-v2-from", type=Path,
                        help="derive a new immutable v2 cohort from an attested v1")
    parser.add_argument("--certificate", type=Path,
                        help="write a strict independent validation attestation")
    args = parser.parse_args()
    if args.verify_only:
        proof = attestation(args.directory, expected=25 * args.seeds)
        if args.certificate:
            with args.certificate.open("x") as output:
                json.dump(proof, output, sort_keys=True, indent=2)
                output.write("\n")
        print("HXB2_COHORT_VALIDATED", 25 * args.seeds,
              proof["cohort_sha256"])
        return
    if args.seeds not in range(1, 129) or args.pairs < 20:
        parser.error("seeds must be 1..128 and pairs at least 20")
    references()
    if args.derive_low_depth_v2_from:
        from .hxb2_lowdepth_v2 import derive
        manifest = derive(args.derive_low_depth_v2_from, args.directory)
    else:
        manifest = generate_cohort(args.directory, args.seeds, args.pairs,
                                   truth_model=haplotypes)
    proof = attestation(args.directory, expected=manifest["samples"])
    if args.certificate:
        with args.certificate.open("x") as output:
            json.dump(proof, output, sort_keys=True, indent=2)
            output.write("\n")
    print("HXB2_COHORT_CREATED_AND_VALIDATED", manifest["samples"],
          proof["cohort_sha256"])


if __name__ == "__main__":
    main()

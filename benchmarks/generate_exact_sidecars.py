"""Create immutable, *separate* exact-coverage sidecars for paired MiCall runs.

Run under the same pinned MiCall Python version as the tested images.
Original per-arm outputs and all input FASTQs are read-only; sidecar output
uses exclusive creation to prevent replacing earlier evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path

from produce_exact_coverage import generate
from micall.utils import exact_coverage


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def generate_sidecars(records_jsonl, fastq_root, output_root, names=None):
    output_root = Path(output_root).resolve()
    fastq_root = Path(fastq_root).resolve()
    if output_root.is_relative_to(fastq_root):
        raise ValueError("sidecar root may not be under source FASTQ tree")
    selected = set(names or ())
    found = set()
    results = []
    with Path(records_jsonl).open() as source:
        for line in source:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("status") != "finished" or record.get("failed") is not False:
                continue
            sample = record["sample"]
            if selected and sample not in selected:
                continue
            if sample in found:
                raise ValueError(f"duplicate completed sample {sample}")
            found.add(sample)
            reads = [
                fastq_root / "samples" / sample / f"{sample}_L001_R{x}_001.fastq.gz"
                for x in (1, 2)]
            if any(not f.is_file() for f in reads):
                raise FileNotFoundError(f"original FASTQ unavailable: {sample}")
            for arm in ("iva", "ivanka"):
                evidence = record.get(arm, {})
                if evidence.get("exit_code") != 0:
                    continue
                folder = Path(evidence["artifact_dir"]).resolve()
                if output_root == folder or output_root.is_relative_to(folder):
                    raise ValueError("sidecar root must not mutate MiCall output")
                conseq = folder / "conseq.csv"
                if not conseq.exists():
                    conseq = folder / "scratch" / "conseq.csv"
                expected = (evidence.get("metrics", {}).get("outputs", {})
                            .get("conseq.csv", {}).get("sha256"))
                if not expected or sha256(conseq) != expected:
                    raise ValueError(f"unverified final MAX source: {sample}/{arm}")
                target = output_root / sample / arm
                target.mkdir(parents=True, exist_ok=True)
                csv_file = target / "exact_coverage.csv"
                report_file = target / "provenance.json"
                if csv_file.exists() or report_file.exists():
                    raise FileExistsError(f"sidecar already exists: {target}")
                result = generate(*reads, conseq, csv_file, overlap_size=70)
                result.update({
                    "source_sample": sample, "source_arm": arm,
                    "source_artifact_dir": str(folder),
                    "source_conseq_sha256": expected,
                    "source_fastq_sha256": [sha256(f) for f in reads],
                    "exact_coverage_sha256": sha256(csv_file),
                    "micall_exact_coverage_module_sha256": sha256(exact_coverage.__file__),
                    "method": "micall.utils.exact_coverage longest MAX, overlap-size=70",
                    "qualification_effect": "none",
                })
                with report_file.open("x") as out:
                    json.dump(result, out, sort_keys=True, indent=2)
                    out.write(chr(10))
                results.append(result)
    if selected - found:
        raise ValueError(f"not all requested samples were successful: {sorted(selected-found)}")
    return results


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("results_jsonl", type=Path)
    p.add_argument("--fastq-root", required=True, type=Path)
    p.add_argument("--output-root", required=True, type=Path)
    p.add_argument("--sample", action="append")
    a = p.parse_args(argv)
    results = generate_sidecars(a.results_jsonl, a.fastq_root,
                                a.output_root, names=a.sample)
    print(json.dumps({"sidecars": len(results),
                      "samples": sorted({x["source_sample"] for x in results}),
                      "qualification_effect": "none"}, indent=2))


if __name__ == "__main__":
    main()

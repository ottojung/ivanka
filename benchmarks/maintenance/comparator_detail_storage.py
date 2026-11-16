"""Lossless, recoverable storage for already-scored MiCall diagnostics."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tarfile

DETAILS = (
    "genome_coverage.csv", "unstitched_genome_coverage.csv",
    "concordance_detailed.csv", "unstitched_concordance_detailed.csv",
    "g2p_aligned.csv", "clipping.csv", "unstitched_clipping.csv",
    "unstitched_nuc_details.csv", "conseq_ins.csv",
    "unstitched_amino_details.csv",
)
ARCHIVE = "checkpointed_details.tar.gz"
PROOF = "checkpointed_details.proof.json"
TEMP = "checkpointed_details.tar.gz.partial"


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha_file(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def flush_dir(parent):
    fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json(path, data):
    tmp = path.with_name(path.name + ".partial")
    if path.exists() or tmp.exists():
        raise ValueError("refuse overwrite of prior proof")
    with tmp.open("x") as stream:
        json.dump(data, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)
    flush_dir(path.parent)


def preserve_files(arm, selected):
    """Hash every non-archived MiCall artifact, including coverage maps."""
    ignored = set(selected) | {ARCHIVE, PROOF, TEMP}
    result = {}
    for path in sorted(arm.rglob("*")):
        if path.is_symlink():
            raise ValueError("symlink in protected MiCall evidence: " + str(path))
        if path.is_file():
            rel = path.relative_to(arm).as_posix()
            if rel not in ignored:
                result[rel] = sha_file(path)
        elif not path.is_dir():
            raise ValueError("unrecognized MiCall output entry")
    for required in ("conseq.csv", "comparator_execution.json"):
        if required not in result:
            raise ValueError("missing protected original MiCall artifact: "+required)
    return result


def select_details(arm, before_time):
    selected = {}
    if arm.is_symlink() or not arm.is_dir():
        raise ValueError("untrusted MiCall arm directory")
    for name in DETAILS:
        path = arm / name
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError("untrusted selected MiCall artifact: "+name)
        st = path.stat()
        if st.st_mtime >= before_time:
            return {}
        if st.st_size > 0:
            selected[name] = {"sha256": sha_file(path),
                              "bytes": st.st_size, "mode": st.st_mode & 0o777,
                              "mtime_ns": st.st_mtime_ns}
    return selected


def verify_originals(arm, selected):
    for name, evidence in selected.items():
        f = arm / name
        if not f.exists() and not f.is_symlink():
            continue
        if (f.is_symlink() or not f.is_file()
                or f.stat().st_size != evidence["bytes"]
                or sha_file(f) != evidence["sha256"]):
            raise ValueError("scientific artifact changed before archive: "+name)


def verify_archive(archive, selected):
    if archive.is_symlink() or not archive.is_file():
        raise ValueError("archive is missing or a symlink")
    actual = {}
    with tarfile.open(archive, "r:gz") as stream:
        for info in stream:
            name = PurePosixPath(info.name)
            if (not info.isfile() or len(name.parts) != 2
                    or name.parts[0] != "details"
                    or name.parts[1] not in selected
                    or name.parts[1] in actual):
                raise ValueError("unsafe archived comparator artifact")
            contents = stream.extractfile(info)
            h = hashlib.sha256()
            n = 0
            for block in iter(lambda stream=contents: stream.read(1048576), b""):
                n += len(block)
                h.update(block)
            actual[name.parts[1]] = {"bytes": n, "sha256": h.hexdigest()}
    wanted = {name: {"bytes": item["bytes"], "sha256": item["sha256"]}
              for name, item in selected.items()}
    if actual != wanted:
        raise ValueError("archived scientific diagnostic does not match source")


def make_archive(arm, proof):
    out = arm / ARCHIVE
    partial = arm / TEMP
    selected = proof["details"]
    if not out.exists():
        if any(not (arm / name).is_file() or (arm / name).is_symlink()
               for name in selected):
            raise ValueError("original details missing before archive exists")
        if partial.exists() or partial.is_symlink():
            partial.unlink()
        with tarfile.open(partial, "w:gz", compresslevel=1) as archive:
            for name in sorted(selected):
                archive.add(arm / name, arcname="details/" + name)
        with partial.open("rb") as stream:
            os.fsync(stream.fileno())
        verify_archive(partial, selected)
        partial.replace(out)
        flush_dir(arm)
    verify_archive(out, selected)
    verify_originals(arm, selected)
    if preserve_files(arm, selected) != proof["protected"]:
        raise ValueError("protected final metrics changed during compression")
    return sha_file(out)


def retire_originals(arm, proof):
    """Remove originals only after complete verified, durable archive."""
    selected = proof["details"]
    verify_archive(arm / ARCHIVE, selected)
    verify_originals(arm, selected)
    if preserve_files(arm, selected) != proof["protected"]:
        raise ValueError("original final MiCall evidence changed")
    for name in selected:
        file = arm / name
        if file.exists():
            file.unlink()
    flush_dir(arm)
    if preserve_files(arm, selected) != proof["protected"]:
        raise ValueError("final MiCall evidence changed during archival")
    verify_archive(arm / ARCHIVE, selected)


def restore_to(arm, destination):
    """Extract into an independent directory, never mutate source results."""
    proof = json.loads((arm / PROOF).read_text())
    archive = arm / ARCHIVE
    verify_archive(archive, proof["details"])
    dest = Path(destination)
    if dest.exists() or dest.is_symlink():
        raise ValueError("refusing to overwrite restored scientific evidence")
    dest.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as files:
        for name in sorted(proof["details"]):
            info = proof["details"][name]
            data = files.extractfile("details/" + name)
            target = dest / name
            with target.open("xb") as output:
                for block in iter(lambda stream=data: stream.read(1048576), b""):
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(target, info["mode"])
            os.utime(target, ns=(info["mtime_ns"], info["mtime_ns"]))
            if sha_file(target) != info["sha256"]:
                raise ValueError("restored scientific output differs")
    flush_dir(dest)
    return sorted(proof["details"])

"""Deny upstream writes and demand immutable fork-commit source provenance."""
import re
from urllib.parse import urlparse

FORK = "ottojung/micall"
UPSTREAM = "cfe-lab/micall"
COMMIT = re.compile(r"^[a-f0-9]{40}$")


def repo_name(remote):
    """Resolve GitHub HTTPS/SSH/short remotes without network access."""
    if not isinstance(remote, str):
        raise ValueError("invalid repository destination")
    target = remote.strip()
    if target.startswith("git@github.com:"):
        target = target[len("git@github.com:"):]
    elif "://" in target:
        parsed = urlparse(target)
        if (parsed.hostname or "").lower() != "github.com" or (
                parsed.scheme not in ("https", "ssh", "git") or
                parsed.query or parsed.fragment or
                parsed.port not in (None, 22, 443)):
            raise ValueError("not an unambiguous GitHub repository")
        target = parsed.path
    elif target.lower().startswith("github.com/"):
        target = target[len("github.com/"):]
    if target.startswith("/"):
        target = target[1:]
    if target.lower().endswith(".git"):
        target = target[:-4]
    target = target.rstrip("/").lower()
    if not re.fullmatch("[a-z0-9_.-]+/[a-z0-9_.-]+", target):
        raise ValueError("invalid owner/repository pair")
    return target


def require_fork_write_destination(remote):
    name = repo_name(remote)
    if name != FORK:
        raise ValueError("refusing MiCall write outside ottojung/MiCall")
    return name


def fork_commit_url(sha):
    if not isinstance(sha, str) or not COMMIT.fullmatch(sha):
        raise ValueError("exact 40-character lowercase MiCall fork SHA required")
    return f"https://github.com/ottojung/MiCall/tree/{sha}"


def validate_fork_image_manifest(record):
    """Format/identity preflight; image contents still need build attestation."""
    if not isinstance(record, dict):
        raise ValueError("MiCall source manifest missing")
    if repo_name(record.get("source_repository")) != FORK:
        raise ValueError("MiCall image source is not ottojung/MiCall")
    source = fork_commit_url(record.get("source_commit"))
    base = fork_commit_url(record.get("baseline_commit"))
    if record.get("source_url") != source or record.get("baseline_url") != base:
        raise ValueError("MiCall provenance links must use exact fork commits")
    for key in ("image_sha256", "dockerfile_sha256"):
        value = record.get(key)
        if not isinstance(value, str) or not re.fullmatch("[a-f0-9]{64}", value):
            raise ValueError("missing immutable container/build digest")
    labels = record.get("oci_labels", {})
    if (labels.get("org.opencontainers.image.source")
            != "https://github.com/ottojung/MiCall"
            or labels.get("org.opencontainers.image.revision")
            != record["source_commit"]):
        raise ValueError("MiCall OCI labels do not match fork commit")
    if record.get("independently_verified_build") is not True:
        raise ValueError("MiCall fork build has not been independently attested")
    return True

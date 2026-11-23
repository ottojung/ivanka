"""Only the Rust assembler executable can differ from the frozen MiCall image."""
import os
from pathlib import Path

from .frozen_contract import IMAGES, sha

IVANKA_IMAGE = IMAGES["ivanka"]
DESTINATION = "/usr/local/bin/ivanka"
SOURCE_ROOT = Path("/workspace")


def candidate_mount(path, expected_sha256):
    original = Path(path)
    if original.is_symlink():
        raise ValueError("candidate must not be a symlink")
    source = original.resolve(strict=True)
    if not source.is_file() or not source.is_relative_to(SOURCE_ROOT):
        raise ValueError("candidate must be a regular workspace-built file")
    if any(c in str(source) for c in (",", ":", "\n", "\x00")):
        raise ValueError("invalid source path for Podman mount")
    if not os.access(source, os.X_OK):
        raise ValueError("Rust candidate binary must be executable")
    if sha(source) != expected_sha256:
        raise ValueError("Rust candidate binary SHA256 changed")
    return ["--mount",
            f"type=bind,src={source},dst={DESTINATION},ro"]


def permitted_image_and_mount(path, binary_sha):
    """Preserve both the frozen clinical source and original image digest."""
    return IVANKA_IMAGE, candidate_mount(path, binary_sha)

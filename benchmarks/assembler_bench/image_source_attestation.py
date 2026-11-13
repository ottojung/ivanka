"""Reverify either immutable MiCall fork format before running any tool."""
import json
from pathlib import Path

from .dedicated_image_attestation import SCHEMA as DEDICATED_SCHEMA
from .dedicated_image_attestation import verify as verify_dedicated
from .fork_image_attestation import verify as verify_shared

SHARED_SCHEMA = "ivanka.assembler-bench.fork-oci-attestation.v1"


def verify(images, attestation, source, base):
    """Use each dedicated branch, never a single shared checkout as its proxy."""
    expected = json.loads(Path(attestation).read_text())
    schema = expected.get("schema")
    if schema == DEDICATED_SCHEMA:
        roots = json.loads(Path(source).read_text())
        actual = verify_dedicated(images, roots, base)
    elif schema == SHARED_SCHEMA:
        actual = verify_shared(images, base, source)
    else:
        raise ValueError("unsupported MiCall image attestation schema")
    if actual != expected:
        raise ValueError("MiCall image/source attestation differs from live audit")
    return actual

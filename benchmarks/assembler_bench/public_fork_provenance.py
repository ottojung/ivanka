"""Cross-check committed fork attestation and every public image identity."""
import json
import re

from .hxb2_preview import sha

SHA = re.compile(r"^[0-9a-f]{64}$")
SOURCE = re.compile(r"^https://github\.com/ottojung/MiCall/tree/[0-9a-f]{40}$")


def check(site, run):
    proof = run.get("micall_fork_provenance", {})
    if proof.get("status") != "verified":
        return
    path = site / "data/live-fork-attestation.json"
    if not path.is_file() or sha(path) != proof.get("attestation_sha256"):
        raise ValueError("missing or tampered source-verified fork attestation")
    att = json.loads(path.read_text())
    if (att.get("base_image_sha256") != proof.get("base_image_sha256")
            or set(att.get("images", {})) != set(run["tools"])
            or set(run["images"]) != set(run["tools"])
            or set(proof.get("images", {})) != set(run["tools"])):
        raise ValueError("public fork image attestation tool/base mismatch")
    for tool, image in att["images"].items():
        shown = proof["images"][tool]
        if (image["image_sha256"] != run["images"][tool]
                or image["image_sha256"] != shown["image_sha256"]
                or image["source_commit"] != shown["source_commit"]
                or image["source_url"] != shown["source_url"]
                or not SOURCE.fullmatch(image["source_url"])
                or not SHA.fullmatch(image["image_sha256"])
                or not SHA.fullmatch(proof["base_image_sha256"])):
            raise ValueError(f"{tool}: forged public source-attestation fields")

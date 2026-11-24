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
    if (proof.get("attestation_schema", att.get("schema"))
            != att.get("schema")):
        raise ValueError("public fork attestation schema mismatch")
    if (att.get("schema") == "ivanka.assembler-bench.dedicated-fork-images.v1"
            and (len({entry.get("source_commit") for entry in
                      att["images"].values()}) != len(att["images"])
                 or any(entry.get("source_branch") !=
                        "bench/assembler-" + name
                        for name, entry in att["images"].items()))):
        raise ValueError("public dedicated fork branches not independent")
    minimal=att.get("schema")=="ivanka.assembler-bench.minimal-fork-images.v1"
    if (minimal and (att.get("baseline_commit")!=proof.get("baseline_commit")
                     or not re.fullmatch("[a-f0-9]{40}",
                                         att.get("baseline_commit",""))
                     or any(not x.get("source_branch","").startswith("bench/minimal-")
                            for x in att.get("images",{}).values()))):
        raise ValueError("minimal source baseline/branch differs")
    # The attestation covers the source-pinned tools of its own cohort; a
    # neutral roster may also contain tools attested by separate evidence.
    if ((not minimal and att.get("base_image_sha256") != proof.get("base_image_sha256"))
            or not set(att.get("images", {})) <= set(run["tools"])
            or set(run["images"]) != set(run["tools"])
            or not set(proof.get("images", {})) <= set(run["tools"])):
        raise ValueError("public fork image attestation tool/base mismatch")
    for tool, image in att["images"].items():
        shown = proof["images"][tool]
        if (image["image_sha256"] != run["images"][tool]
                or image["image_sha256"] != shown["image_sha256"]
                or image["source_commit"] != shown["source_commit"]
                or image["source_url"] != shown["source_url"]
                or shown.get("source_branch") != image.get("source_branch")
                or not SOURCE.fullmatch(image["source_url"])
                or not SHA.fullmatch(image["image_sha256"])
                or (not minimal and
                    not SHA.fullmatch(proof["base_image_sha256"]))):
            raise ValueError(f"{tool}: forged public source-attestation fields")

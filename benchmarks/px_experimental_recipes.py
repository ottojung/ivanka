"""Fail-closed validation of source-only PX build recipes.

These recipes are plans, not evidence: they never assert an image digest, a
native hash, a pilot result or a qualification outcome. They exist so a later
guarded build job can be reviewed before it consumes shared-filesystem headroom.
"""
import json
import re
from pathlib import Path

RECIPES = Path(__file__).resolve().parent.parent / "docs/bench/px-experimental-recipes"
SCHEMA = "ivanka.exploratory.recipe.v1"
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
SHA64 = re.compile(r"[a-f0-9]{64}\Z")
FROZEN_PARENT = "da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad"
MASTER = "8458f9e5d34c39a6694b1fb6a40e055d7ce89553"
FORBIDDEN_FLAG = re.compile(
    r"(--reference|--ref\s*=|--panel\b|hxb2\.fasta|truth\.fasta|alignment_score)", re.I)
PRIVATE_PATH = re.compile(r"/workspace/|/home/lubko/|/tmp/opencode/")
CONTRACT = {"one_worker": True,
            "min_free_bytes": 34359738368, "container_memory_bytes": 4000000000,
            "wall_seconds": 2400}
EXPECTED = {
    "ray": ("9e02a9205fc338e1be4f0cd4a8dd4a13b406ae88",
            "621dfe8454dc96d49f405e413cb759d3f48790b2"),
    "tadpole": ("baaaa082c1c1eb62b203baf80b14031facde4b40",
                "fb1a2727b7b4994ecae0ddc362d4ed8148307b20"),
}
NATIVE_TOOLS = ("soapdenovo2", "unicycler", "penguin", "savage-denovo")
FILES = {"ray": "ray-rayplatform-c8d9fe2.json",
         "tadpole": "tadpole-minimal-jre.json",
         "native-requirements": "native-requirements.json",
         "ray-disk-admission-design": "ray-disk-admission-design.json"}


def _document(name):
    if name not in FILES:
        raise ValueError("unknown recipe: " + name)
    path = RECIPES / FILES[name]
    if not path.is_file():
        raise ValueError("missing recipe: " + name)
    return json.loads(path.read_text()), path


def checked(name):
    """Return a validated recipe document or fail closed."""
    data, path = _document(name)
    if data.get("schema") != SCHEMA or data.get("claim") != "measured-data-only":
        raise ValueError("recipe schema or claim drift: " + name)
    if data.get("frozen_parent") != FROZEN_PARENT or data.get(
            "frozen_upstream_master") != MASTER:
        raise ValueError("frozen base drift: " + name)
    # A legacy `max_incremental_bytes` in a historical recipe is the removed
    # project ceiling; accept and ignore it, preserving the old bytes.
    contract = dict(data.get("resource_contract") or {})
    contract.pop("max_incremental_bytes", None)
    if contract != CONTRACT:
        raise ValueError("resource contract drift: " + name)
    if PRIVATE_PATH.search(path.read_text()):
        raise ValueError("host-private path in portable recipe: " + name)
    if FORBIDDEN_FLAG.search(path.read_text()):
        raise ValueError("reference/evaluator flag in recipe: " + name)
    if not str(data.get("status", "")).startswith("source-only"):
        raise ValueError("recipe claims an unbuilt result: " + name)
    if name == "native-requirements":
        tools = data.get("tools", {})
        if set(tools) != set(NATIVE_TOOLS):
            raise ValueError("native requirements roster drift")
        for tool, item in tools.items():
            if not SHA40.fullmatch(item.get("adapter_commit", "")):
                raise ValueError("invalid adapter pin: " + tool)
            if not item.get("source_repo", "").startswith("https://github.com/"):
                raise ValueError("invalid source pin: " + tool)
        return data
    if name == "ray-disk-admission-design":
        budget = data.get("measured_budget", {})
        # A legacy `cap_bytes` in a historical recipe is accepted and ignored;
        # it is not a bound on current source-only build plans.
        if (budget.get("reservation_bytes") < 1 << 30
                or budget.get("headroom_bytes", 0) < 0
                or len(data.get("attempts", [])) != 3):
            raise ValueError("Ray budget evidence drift")
        return data
    if name not in EXPECTED:
        raise ValueError("unknown recipe: " + name)
    adapter, source = EXPECTED[name]
    if (data.get("tool") != name or data.get("adapter_commit") != adapter
            or data.get("source_commit") != source):
        raise ValueError("pin drift: " + name)
    if not data.get("root_cause") or not (data.get("donor_steps")
                                          or data.get("smaller_layer_plan")):
        raise ValueError("recipe lacks its reason or steps: " + name)
    return data


def checked_patch():
    """Verify the SOAPdenovo2 non-PIC linker patch stays link-only."""
    path = RECIPES / "soapdenovo2-nopic.patch"
    text = path.read_text()
    if PRIVATE_PATH.search(text) or FORBIDDEN_FLAG.search(text):
        raise ValueError("patch contains private paths or reference flags")
    if "LINK_FLAGS = -no-pie" not in text or text.count(
            "$(LINK_FLAGS) sparsePregraph/") < 3:
        raise ValueError("non-PIC link fix missing from patch")
    if "CFLAGS" in text and "-no-pie" in text.split("CFLAGS", 1)[1][:80]:
        raise ValueError("patch must not change C object compilation")
    return text

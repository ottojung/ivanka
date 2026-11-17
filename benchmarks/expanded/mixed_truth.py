"""Replayable HCV/HIV and HCV/V3 biological mixtures for benchmark only."""
import hashlib
import json
from pathlib import Path
import random

from .hxb2_truth import plan, references, synthesize
from .synthetic import DNA, fingerprint, pick_alt

SOURCE = Path(__file__).parent / "references"
META = SOURCE / "mixed-sources-20261117.json"
FAMILIES = {
    "hcv_hiv_15pct": ("hiv", (0.85, 0.15)),
    "hcv_hiv_30pct": ("hiv", (0.70, 0.30)),
    "hcv_v3_15pct": ("v3", (0.85, 0.15)),
    "hcv_v3_30pct": ("v3", (0.70, 0.30)),
}


def sources():
    spec = json.loads(META.read_text())
    if spec.get("schema") != "ivanka.synthetic.mixed_sources.v1":
        raise ValueError("unrecognized mixed-virus source catalog")
    hcv = spec["hcv"]
    file = SOURCE / hcv["file"]
    if fingerprint(file) != hcv["fasta_sha256"]:
        raise ValueError("unpinned HCV source FASTA")
    sequence = "".join(line for line in file.read_text().splitlines()
                       if not line.startswith(">"))
    hxb2 = "".join(line for line in
                   (SOURCE / spec["v3"]["source_file"]).read_text().splitlines()
                   if not line.startswith(">"))
    v3 = spec["v3"]
    segment = hxb2[v3["zero_based_start_inclusive"]:
                   v3["zero_based_end_exclusive"]]
    for seq, record in ((sequence, hcv), (segment, v3)):
        if (not seq or set(seq) - set(DNA)
                or len(seq) != record["length"]
                or hashlib.sha256(seq.encode()).hexdigest()
                   != record["sequence_sha256"]):
            raise ValueError("mixed-virus source sequence changed")
    from .hxb2_truth import references as verify_hiv
    verify_hiv()
    return sequence, segment, fingerprint(META)


def mutation_plan(sequence, seed, group, component):
    token = f"ivanka-mixed-v1:{group}:{seed}:{component}"
    identity = int.from_bytes(
        hashlib.sha256(token.encode()).digest()[:8], "big")
    rng = random.Random(identity)
    count = rng.randrange(int(len(sequence) * 0.05) + 1)
    sites = rng.sample(range(len(sequence)), count)
    changes = [{"site": site, "base": pick_alt(sequence[site], rng)}
               for site in sites]
    return {"seed": identity, "unmutated_length": len(sequence),
            "mutations": changes}


def apply_mutations(sequence, recipe):
    if (len(sequence) != recipe["unmutated_length"]
            or len(recipe["mutations"]) > len(sequence) * 0.05):
        raise ValueError("mutation recipe violates length or rate bound")
    result = list(sequence)
    seen = set()
    for change in recipe["mutations"]:
        i, base = change["site"], change["base"]
        if (type(i) is not int or i not in range(len(result))
                or i in seen or base not in DNA or base == result[i]):
            raise ValueError("malformed mutation recipe")
        seen.add(i)
        result[i] = base
    return "".join(result)


def haplotypes(family, seed):
    if family not in FAMILIES or type(seed) is not int or seed < 0:
        raise ValueError("unknown mixed-virus family or seed")
    target, fractions = FAMILIES[family]
    group = "hcv_" + target
    hcv, v3, digest = sources()
    first = mutation_plan(hcv, seed, group, "hcv")
    mutated_hcv = apply_mutations(hcv, first)
    if target == "hiv":
        records, _ = references()
        second = plan("clonal", seed + 1000, 0, records, revision=2)
        mutated_other = synthesize(second, records)
    else:
        second = mutation_plan(v3, seed, group, "v3")
        mutated_other = apply_mutations(v3, second)
    ancestry = {"schema": "ivanka.synthetic.mixed_ancestry.v1",
                "source_catalog_sha256": digest, "group": group,
                "hcv_recipe": first, "second_recipe": second,
                "second_kind": target}
    return [mutated_hcv, mutated_other], list(fractions), mutated_hcv, ancestry


def validate(case):
    case = Path(case)
    manifest = json.loads((case / "manifest.json").read_text())
    if manifest.get("schema") != "ivanka.expanded.synthetic.multi_viral.v1":
        raise ValueError("not a versioned mixed-virus case")
    genomes, fractions, _, ancestry = haplotypes(
        manifest["family"], manifest["seed"])
    if (manifest.get("mixed_ancestry") != ancestry
            or manifest.get("nominal_fractions") != fractions
            or manifest.get("truth_model_revision") != 3):
        raise ValueError("mixed-virus ancestry or abundances modified")
    truth = case / manifest["hidden_truth_file"]
    observed = ["".join(block.splitlines()[1:]) for block
                in truth.read_text().split(">") if block.strip()]
    if observed != genomes or manifest["haplotype_count"] != len(genomes):
        raise ValueError("mixed-virus truths differ from source recipes")
    for relpath, expected in manifest["sha256"].items():
        if fingerprint(case / relpath) != expected:
            raise ValueError("mixed-virus input digest mismatch")
    return True

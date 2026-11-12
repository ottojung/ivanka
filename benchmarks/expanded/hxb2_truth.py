"""Pinned HXB2/subtype homologous recombinant biological truth, never an input.

Only bench generation and independent truth scoring may open these files.
"""
import hashlib
import json
from pathlib import Path
import random

from .synthetic import DNA, FAMILIES, fingerprint, pick_alt

REFERENCES = Path(__file__).parent / "references"
ACCESSIONS = ("K03455.1", "U46016.1", "MH705157.1")
FRACTIONS = {
    "minority_5pct": [0.95, 0.05],
    "minority_30pct": [0.7, 0.3],
    "equal_strains": [0.5, 0.5],
    "complex_mixture": [0.65, 0.25, 0.08, 0.02],
}


def references():
    info = json.loads((REFERENCES / "manifest.json").read_text())
    if set(info["accessions"]) != set(ACCESSIONS):
        raise ValueError("unexpected HIV subtype reference panel")
    for accession, record in info["accessions"].items():
        if fingerprint(REFERENCES / f"{accession}.fasta") != record["sha256"]:
            raise ValueError("unpinned source reference " + accession)
    aligned = REFERENCES / info["alignment"]["file"]
    if fingerprint(aligned) != info["alignment"]["sha256"]:
        raise ValueError("unpinned homologous sequence alignment")
    records = {}
    name = None
    for line in aligned.read_text().splitlines():
        if line.startswith(">"):
            name = line[1:].split()[0]
            records[name] = ""
        elif name is None:
            raise ValueError("invalid alignment FASTA")
        else:
            records[name] += line.strip().upper()
    if set(records) != set(ACCESSIONS) or len({len(x) for x in records.values()}) != 1:
        raise ValueError("wrong biological reference alignment")
    for accession, sequence in records.items():
        source = "".join(x for x in (REFERENCES / f"{accession}.fasta").read_text()
                         .splitlines() if not x.startswith(">")).upper()
        if sequence.replace("-", "") != source or set(source) - set(DNA):
            raise ValueError("parent sequence does not match pinned accession")
    return records, info["alignment"]["sha256"]


def seeded(family, sample, haplotype):
    token = f"ivanka-hxb2-v1:{family}:{sample}:haplotype:{haplotype}".encode()
    return int.from_bytes(hashlib.sha256(token).digest()[:8], "big")


def plan(family, sample, haplotype, records):
    """A no-replacement sample of uniform mutations independent of sequence."""
    rng = random.Random(seeded(family, sample, haplotype))
    length = len(records[ACCESSIONS[0]])
    # Every recombinant starts with an HXB2 block and introduces one or
    # more randomly sampled other subtype blocks on aligned coordinates.
    breaks = [] if haplotype == 0 and family == "clonal" else sorted(
        rng.sample(range(600, length - 600), rng.randint(1, 3)))
    limits = [0, *breaks, length]
    parents = [ACCESSIONS[0]]
    for _ in breaks:
        parents.append(rng.choice(ACCESSIONS[1:]))
    segments = [{"start": a, "end": b, "accession": accession}
                for a, b, accession in zip(limits, limits[1:], parents)]
    source = "".join(records[s["accession"]][s["start"]:s["end"]]
                     for s in segments).replace("-", "")
    count = rng.randrange(int(len(source) * .05) + 1)
    sites = rng.sample(range(len(source)), count)
    changes = [{"site": site, "base": pick_alt(source[site], rng)}
               for site in sites]
    return {"segments": segments, "mutations": changes, "seed": seeded(
        family, sample, haplotype), "unmutated_length": len(source)}


def synthesize(recipe, records):
    base = list("".join(
        records[s["accession"]][s["start"]:s["end"]]
        for s in recipe["segments"]).replace("-", ""))
    if len(base) != recipe["unmutated_length"]:
        raise ValueError("ancestry changes the expected truth length")
    if len(recipe["mutations"]) > len(base) * .05:
        raise ValueError("more than 5% truth mutations")
    sites = set()
    for mutation in recipe["mutations"]:
        site, value = mutation["site"], mutation["base"]
        if (type(site) is not int or site not in range(len(base))
                or site in sites or value not in DNA or value == base[site]):
            raise ValueError("invalid substitution or mutation site")
        sites.add(site)
        base[site] = value
    return "".join(base)


def haplotypes(family, sample):
    if family not in FAMILIES or type(sample) is not int or sample < 0:
        raise ValueError("unregistered synthetic family or seed")
    records, aligned_hash = references()
    fractions = FRACTIONS.get(family, [1.0])
    recipes = [plan(family, sample, i, records) for i in range(len(fractions))]
    genome = [synthesize(x, records) for x in recipes]
    # Technical contaminants are also derived from allowed recombinant truth.
    contamination = synthesize(plan(family, sample, 99, records), records)
    provenance = {
        "schema": "ivanka.expanded.hxb2_ancestry.v1",
        "source_alignment_sha256": aligned_hash, "accessions": list(ACCESSIONS),
        "truth_mutation_policy": "uniform sites without replacement, <=5%",
        "recipes": recipes,
        "contamination_recipe": plan(family, sample, 99, records),
    }
    return genome, fractions, contamination, provenance


def validate(case):
    """Fail closed if hidden truth or sampled ancestry drifted."""
    case = Path(case)
    manifest = json.loads((case / "manifest.json").read_text())
    family, sample = manifest["family"], manifest["seed"]
    genomes, fractions, contamination, expected = haplotypes(family, sample)
    if (manifest.get("schema") != "ivanka.expanded.synthetic.hxb2.v1"
            or manifest.get("hxb2_ancestry") != expected
            or manifest.get("nominal_fractions") != fractions):
        raise ValueError("missing, nonrandom or unpinned HXB2 ancestry")
    truth = case / manifest["hidden_truth_file"]
    observed = ["".join(line for line in block.splitlines()[1:])
                for block in truth.read_text().split(">") if block.strip()]
    if observed != genomes:
        raise ValueError("synthetic truth not reproducible from HXB2 provenance")
    if len(genomes) != manifest["haplotype_count"] or not contamination:
        raise ValueError("missing truth or source-permitted contaminant")
    for relpath, expected_sha in manifest["sha256"].items():
        if fingerprint(case / relpath) != expected_sha:
            raise ValueError("synthetic file changed after generation")
    return True

"""Validate public seven-fork-branch container identity before publishing."""
import json
import re

from benchmarks.expanded.adapters import ASSEMBLERS, PROGRAMS

SOURCE = "https://github.com/ottojung/MiCall"
SCHEMA = "ivanka.assembler-bench.dedicated-fork-images.v1"
STATUS = "SEVEN_INDEPENDENT_BRANCH_IMAGES_VERIFIED"
SHA40 = re.compile("^[a-f0-9]{40}$")
SHA64 = re.compile("^[a-f0-9]{64}$")


def check(site):
    """A build inventory is never a substitute for an eligible benchmark run."""
    source = site / "data/dedicated-images.json"
    obj = json.loads(source.read_text())
    if (obj.get("schema") != SCHEMA or obj.get("status") != STATUS
            or obj.get("source_repository") != SOURCE
            or set(obj.get("images", {})) != set(ASSEMBLERS)):
        raise ValueError("missing/ineligible dedicated fork-image inventory")
    base_sha = obj.get("baseline_commit", "")
    base_id = obj.get("base_image_sha256", "")
    if (not SHA40.fullmatch(base_sha) or not SHA64.fullmatch(base_id)
            or obj.get("baseline_url") != SOURCE+"/tree/"+base_sha):
        raise ValueError("invalid common fork MiCall base")
    hashes = obj.get("installed_modules_sha256", {})
    if (not isinstance(hashes, dict) or not hashes
            or any(not isinstance(v,str) or not SHA64.fullmatch(v)
                   for v in hashes.values())):
        raise ValueError("unverifiable installed MiCall modules")
    images = set()
    commits = set()
    for name in ASSEMBLERS:
        item = obj["images"][name]
        sha = item.get("source_commit", "")
        image = item.get("image_sha256", "")
        binaries = item.get("executables_sha256", {})
        if (item.get("selected_assembler") != name or
                item.get("source_branch") != "bench/assembler-"+name or
                item.get("source_repository") != SOURCE or
                not SHA40.fullmatch(sha) or
                item.get("source_url") != SOURCE+"/tree/"+sha or
                item.get("baseline_commit") != base_sha or
                item.get("baseline_url") != obj["baseline_url"] or
                not SHA64.fullmatch(image) or
                not SHA64.fullmatch(item.get("dockerfile_sha256", "")) or
                item.get("installed_modules_sha256") != hashes or
                not isinstance(binaries,dict) or
                set(binaries) != (set(PROGRAMS[name])|
                                   set(PROGRAMS["iva"])) or
                any(not SHA64.fullmatch(value)
                    for value in binaries.values())):
            raise ValueError(f"{name}: missing separate source/image provenance")
        if sha in commits or image in images:
            raise ValueError("assembler branches or images are not distinct")
        images.add(image)
        commits.add(sha)
    if re.search(r"/workspace/|/home/|\.fastq|patient[-_]?id",
                 source.read_text(),re.IGNORECASE):
        raise ValueError("private identifiers in public build inventory")
    return len(images)

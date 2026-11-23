"""The original seven MiCall assembler arms have a single immutable baseline."""
import hashlib
import json
import subprocess
from pathlib import Path

COMMIT = "8458f9e5d34c39a6694b1fb6a40e055d7ce89553"
TREE = "4174e1cd850352788f7de5fe6cd66f12fbe27a70"
MANIFEST = "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f"
ATTESTATION = "7a996476751594d2878e31412c8590d0c27193fd543f2de687b36cda9163a8a5"
IMAGES = {
    "abyss": "4041a048297a9101fc15652c9523a21be09f4a0bd10b674ed9dbfd53b7f5b206",
    "haploflow": "a8c1a501c92d40df93b8ecd0e1800c8586624b0d4f7412c02d9cc3fd32f9c250",
    "iva": "16afbb25642dae3ce9e09eeaf22ddc3c41ecf02f71fadef910494ef564d39fd9",
    "ivanka": "da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad",
    "megahit": "905ef4d395ad14a2110792173a38e88deaa7f64b56b19368f9714f84f1e9cc46",
    "spades": "a0e7e98d143499fad423c2430aec061871015ee644b7d93d9cd0e29dc84c6c64",
    "velvet": "89ab32ea07c367d8823237c4e5d0b4801e55ba80cd24fa608f97c087514e051c",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_images(root):
    root = Path(root)
    if sha(root / "minimal-images.json") != MANIFEST:
        raise ValueError("frozen seven-image manifest changed")
    if json.loads((root / "minimal-images.json").read_text()) != IMAGES:
        raise ValueError("frozen seven image identities changed")
    p = root / "minimal-images-attestation-v2.json"
    if sha(p) != ATTESTATION:
        raise ValueError("frozen source attestation changed")
    a = json.loads(p.read_text())
    if a["baseline_commit"] != COMMIT or set(a["images"]) != set(IMAGES):
        raise ValueError("frozen common MiCall source changed")
    for name, image in a["images"].items():
        if image["baseline_commit"] != COMMIT or image["image_sha256"] != IMAGES[name]:
            raise ValueError("MiCall baseline/image changed: " + name)
        if any(f.startswith(("micall/drivers/", "micall/utils/"))
               for f in image["changed_files"]):
            raise ValueError("shared MiCall implementation changed: " + name)
    return a


def verify_source(checkout, require_commit=True):
    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(checkout), *args], text=True).strip()
    if git("rev-parse", "HEAD^{tree}") != TREE:
        raise ValueError("common MiCall source tree differs from frozen baseline")
    if require_commit and git("rev-parse", "HEAD") != COMMIT:
        raise ValueError("new benchmark requires exactly frozen baseline commit")
    if git("status", "--porcelain"):
        raise ValueError("MiCall checkout contains uncommitted changes")
    return COMMIT

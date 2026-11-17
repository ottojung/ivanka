"""Host-only attestation for every original physical read pair.

The frozen TSV is necessary but insufficient: original local FASTQ bytes
must also still match their upstream MD5s, sizes, and new SHA256 witnesses.
"""
import csv
import hashlib
import json
from pathlib import Path

from .real_matrix import MANIFEST

SCHEMA="ivanka.assembler-bench.authentic-physical-inputs.v1"

def hash_pair(path):
    md5=hashlib.md5(usedforsecurity=False)
    sha=hashlib.sha256()
    size=0
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            size+=len(block)
            md5.update(block)
            sha.update(block)
    return md5.hexdigest(),sha.hexdigest(),size

def sample_paths(root,sample):
    directory=(root/"samples"/sample).resolve(strict=True)
    if not directory.is_relative_to((root/"samples").resolve()):
        raise ValueError("unsafe original physical sample path")
    result=[]
    for mate in (1,2):
        found=list(directory.glob(f"*_R{mate}_001.fastq.gz"))
        if len(found)!=1 or found[0].is_symlink():
            raise ValueError("missing, duplicate or linked original FASTQ mate")
        result.append(found[0])
    return result

def attest(data, *, expected=198, manifest_sha=MANIFEST):
    root=Path(data).resolve(strict=True)
    manifest=root/"manifest.tsv"
    if hashlib.sha256(manifest.read_bytes()).hexdigest()!=manifest_sha:
        raise ValueError("original physical cohort TSV changed")
    with manifest.open(newline="") as handle:
        rows=list(csv.DictReader(handle,delimiter="\t"))
    if (len(rows)!=expected
            or len({row["sample"] for row in rows})!=expected):
        raise ValueError("not exactly the original distinct physical samples")
    attestations={}
    total=0
    for row in rows:
        name=row["sample"]
        readings=[]
        for mate,path in enumerate(sample_paths(root,name),1):
            md5,sha,size=hash_pair(path)
            if (md5!=row[f"local_md5_r{mate}"]
                    or md5!=row[f"kive_md5_r{mate}"]
                    or size!=int(row[f"r{mate}_bytes"])):
                raise ValueError(f"physical FASTQ content differs for {name} mate {mate}")
            total+=size
            readings.append({"sha256":sha,"bytes":size})
        attestations[name]=readings
    packed=json.dumps(attestations,sort_keys=True,separators=(",",":")).encode()
    hxb2=root/"hxb2.fasta"
    return {"schema":SCHEMA, "sample_count":len(attestations),
            "total_fastq_bytes":total,"manifest_sha256":manifest_sha,
            "input_pairs_sha256":hashlib.sha256(packed).hexdigest(),
            "hxb2_sha256":hashlib.sha256(hxb2.read_bytes()).hexdigest()}

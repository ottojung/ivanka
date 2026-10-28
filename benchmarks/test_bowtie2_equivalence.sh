#!/bin/sh
set -eu
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
python3 - "$work" <<'PYCODE'
import random,sys
from pathlib import Path
p=Path(sys.argv[1])
rng=random.Random(43771)
ref="".join(rng.choice("ACGT") for _ in range(8000))
(p/"reference.fa").write_text(">synthetic\n"+ref+"\n")
for mate in (1,2):
    with (p/f"r{mate}.fq").open("w") as out:
        for i in range(5000):
            x=250+(i*71)%7000
            seq=(ref[x:x+100] if mate==1 else
                 ref[x+220:x+320].translate(str.maketrans("ACGT","TGCA"))[::-1])
            out.write(f"@synthetic_{i}\n{seq}\n+\n"+("I"*100)+"\n")
PYCODE
/opt/bowtie2/bowtie2-build "$work/reference.fa" "$work/ref" >/dev/null 2>&1
for program in /opt/bowtie2/bowtie2-original /opt/bowtie2/bowtie2; do
    case "$program" in *original) suffix=one;; *) suffix=eight;; esac
    "$program" --wrapper micall-0 --quiet -x "$work/ref"        -1 "$work/r1.fq" -2 "$work/r2.fq"        --no-hd --local -X 1200 -p 1 >"$work/$suffix.sam"
done
if ! cmp -s "$work/one.sam" "$work/eight.sam"; then
    echo "Multithread Bowtie2 changed synthetic mapped SAM output" >&2
    exit 1
fi
echo "Equivalent synthetic paired-end SAM: 5000 pairs, 1 vs 8 threads, identical byte-for-byte"

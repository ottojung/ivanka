#!/usr/bin/env python3
"""Benchmark-only Bowtie2 thread override; preserve read order via --reorder.

MiCall specifies -p 1. Only replace that concurrency flag, never mapping
scores/reference/reads. Both IVA and Riva benchmark images must share this
same immutable base image.
"""
import os
import sys

def rewritten(argv, threads):
    argv = list(argv)
    changed = False
    for i in range(len(argv) - 1):
        if argv[i] == "-p" and argv[i+1] == "1":
            argv[i+1] = str(threads)
            changed = True
    if changed and threads > 1 and "--reorder" not in argv:
        argv.append("--reorder")
    return argv

if __name__ == "__main__":
    n=int(os.environ.get("RIVA_BOWTIE_THREADS","8"))
    if n<1 or n>32:
        raise SystemExit("RIVA_BOWTIE_THREADS must be between 1 and 32")
    os.execv("/opt/bowtie2/bowtie2-original",
             ["/opt/bowtie2/bowtie2-original"] + rewritten(sys.argv[1:],n))

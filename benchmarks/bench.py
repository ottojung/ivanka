#!/usr/bin/env python3
"""Real-data Riva alpha benchmark. Keeps all private sample results outside Git.

Biology and code paths are intentionally identical for IVA and Riva AFTER the
assembler boundary: >=600 bp raw contigs -> MiCall referenceless stitcher (with
read support) -> fixed HXB2 global PairwiseAligner score.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from acceptance import accept_sample, reference_fidelity, STRUCTURAL_ROLES

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("RIVA_DATA", "/workspace/denovo-example-io-1"))
CACHE = Path(os.environ.get("RIVA_BENCH_CACHE", "/workspace/riva-benchmark-cache"))
RESULTS = ROOT / "benchmark-results"
MICALL = Path(os.environ.get("MICALL_REPO", "/workspace/qai-repo/repos/MiCall"))
sys.path.insert(0, str(MICALL))
try:
    from Bio import SeqIO
    from Bio.Align import PairwiseAligner
    from micall.utils.referenceless_contig_stitcher import (
        build_read_index, referenceless_contig_stitcher,
    )
except ImportError as e:
    raise SystemExit(f"Benchmark dependency unavailable: {e}. Configure .venv and MICALL_REPO.") from e

MIN_LENGTH = 600
ABORT = False
def stop(signum, frame):
    global ABORT
    ABORT = True
    raise KeyboardInterrupt(f"signal {signum}")
signal.signal(signal.SIGTERM, stop)

def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+".new")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True)+"\n")
    tmp.replace(path)

def read_manifest():
    with (DATA/"manifest.tsv").open(newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))

def input_files(row):
    folder = DATA/"samples"/row["sample"]
    r1 = folder / (row["sample"]+"_L001_R1_001.fastq.gz")
    r2 = folder / (row["sample"]+"_L001_R2_001.fastq.gz")
    if not r1.is_file() or not r2.is_file():
        raise FileNotFoundError(f"Missing FASTQ for {row['sample']}")
    return r1,r2

def original_iva(row):
    folder = DATA/"samples"/row["sample"]
    run_id=row["kive_run_id"]
    csv_path=folder / f"unstitched_contigs_{run_id}.csv"
    with csv_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if "contig" not in (reader.fieldnames or []):
            raise ValueError(f"missing contig column: {csv_path}")
        return [x["contig"].upper() for x in reader if x.get("contig")]

def fasta_sequences(path):
    return [str(rec.seq).upper() for rec in SeqIO.parse(path, "fasta")]

def to_fasta(path, sequences):
    with path.open("w") as handle:
        for n,seq in enumerate(sequences,1):
            handle.write(f">contig_{n}\n")
            for i in range(0,len(seq),80):
                handle.write(seq[i:i+80]+"\n")

def prepare_reads(row, cached_only=False):
    """Reuse deterministic MiCall preprocessing; don't silently use raw BaseCalls."""
    if cached_only:
        folder = CACHE / row["sample"]
        r1, r2 = (folder / "trimmed_R1.fastq", folder / "trimmed_R2.fastq")
        marker = folder / "trim-complete.json"
        if not marker.is_file() or not r1.is_file() or not r2.is_file():
            raise FileNotFoundError("Missing original cached reads for " + row["sample"])
        provenance = json.loads(marker.read_text())
        if provenance.get("micall_source") != micall_commit():
            raise ValueError("Cached MiCall preprocessing version has changed")
        return r1, r2
    # Private cached output; no patient data added to repository.
    r1,r2=input_files(row)
    cache_dir = CACHE/row["sample"]
    cache_dir.mkdir(parents=True, exist_ok=True)
    out1=cache_dir/"trimmed_R1.fastq"
    out2=cache_dir/"trimmed_R2.fastq"
    marker=cache_dir/"trim-complete.json"
    source_hash=hashlib.sha256(json.dumps(
        [str(r1),r1.stat().st_size,str(r2),r2.stat().st_size,row["project"]],
        sort_keys=True).encode()).hexdigest()
    if marker.is_file() and out1.is_file() and out2.is_file():
        old=json.loads(marker.read_text())
        if old.get("source_hash")==source_hash and old.get("micall_source")==micall_commit():
            return out1,out2
    from micall.core.trim_fastqs import trim
    bad_cycles=cache_dir/"bad_cycles.csv"
    bad_cycles.write_text("tile,cycle\n")
    temp1=cache_dir/"trimmed_R1.partial.fastq"
    temp2=cache_dir/"trimmed_R2.partial.fastq"
    for f in (temp1,temp2): f.unlink(missing_ok=True)
    trim([str(r1),str(r2)],str(bad_cycles),[str(temp1),str(temp2)],
         use_gzip=True,project_code=row["project"])
    temp1.replace(out1)
    temp2.replace(out2)
    write_atomic(marker, {"source_hash":source_hash,"micall_source":micall_commit(),
                          "project":row["project"],"method":"micall.core.trim_fastqs.trim"})
    return out1,out2

def micall_commit():
    try:
        return subprocess.check_output(["git","-C",str(MICALL),"rev-parse","HEAD"], text=True).strip()
    except Exception:
        return "unknown"

def stitch_and_score(seqs, read_index, read_length, reference, out_dir, arm):
    out_dir.mkdir(parents=True,exist_ok=True)
    filt=[seq for seq in seqs if len(seq)>=MIN_LENGTH]
    raw=out_dir/f"{arm}.raw.fasta"
    filtered=out_dir/f"{arm}.filtered.fasta"
    stitched=out_dir/f"{arm}.stitched.fasta"
    to_fasta(raw,seqs)
    to_fasta(filtered,filt)
    if filt:
        with filtered.open() as h_in, stitched.open("w") as h_out:
            referenceless_contig_stitcher(
                h_in,h_out,read_index=read_index,minimum_read_depth=1,
                read_length=read_length)
        result=fasta_sequences(stitched)
    else:
        stitched.write_text("")
        result=[]
    aligner=PairwiseAligner()
    aligner.mode="global"
    aligner.end_gap_score=-1
    # These match MiCall's make_stats.py default PairwiseAligner settings.
    scores=[float(aligner.score(reference,s)) for s in result]
    return {
        "raw_count":len(seqs),"raw_longest":max((len(s) for s in seqs),default=0),
        "filtered_count":len(filt),"stitched_count":len(result),
        "stitched_longest":max((len(s) for s in result),default=0),
        "hxb2_score":max(scores,default=None),"per_contig_scores":scores,
    }

def run():
    ap=argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("baseline","riva","all"),default="all")
    ap.add_argument("--only", default=None,help="Exact sample ID (private dataset)")
    ap.add_argument("--riva",default=str(ROOT/"target/release/riva"))
    ap.add_argument("--cached-inputs",action="store_true",
                    help="Pin the original private seven-sample acceptance set to cached trimmed reads, not a mutable source manifest")
    args=ap.parse_args()
    if args.cached_inputs:
        saved = json.loads((CACHE/"baselines.json").read_text())
        # Canonical acceptance order from the cache, independent of the
        # mutable source manifest. Never synthesize new baselines here.
        manifest = [{"sample": sample, "kive_run_id": entry["run_id"]}
                    for sample, entry in saved.items()]
    else:
        manifest=read_manifest()
    if args.only:
        manifest=[r for r in manifest if r["sample"]==args.only]
        if not manifest: raise SystemExit("No selected sample matches --only")
    RESULTS.mkdir(exist_ok=True)
    ref_recs=list(SeqIO.parse(DATA/"hxb2.fasta","fasta"))
    if len(ref_recs)!=1: raise ValueError("Reference must have exactly one HXB2 sequence")
    ref=str(ref_recs[0].seq).upper()
    if len(ref)!=9719 or "K03455" not in ref_recs[0].id:
        raise ValueError("Wrong HXB2 reference identity")
    reference_hash=hashlib.sha256(ref.encode()).hexdigest()
    baseline_path=CACHE/"baselines.json"
    baselines=json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    roles_path=CACHE/"roles.json"
    if args.mode != "baseline":
        if not roles_path.is_file():
            raise ValueError("Missing private benchmark role config: " + str(roles_path))
        roles=json.loads(roles_path.read_text())
        if any(r["sample"] not in roles for r in manifest):
            raise ValueError("Incomplete private benchmark role config")
    else:
        roles={}
    # Every JSONL record carries its invoking binary identity. Never combine
    # best scores from unrelated experimental builds into a fictitious 7/7 run.
    invocation_id=f"{int(time.time())}-{os.getpid()}"
    binary_sha256=None
    if args.mode in ("riva", "all"):
        binary_sha256=hashlib.sha256(Path(args.riva).read_bytes()).hexdigest()
    print(f"Invocation: {invocation_id} Riva SHA256: {binary_sha256 or 'baseline-only'}",flush=True)
    start=time.monotonic()
    records=[]
    current=RESULTS/"results.jsonl"
    with current.open("a",buffering=1) as report:
        for row in manifest:
            sample=row["sample"]
            if ABORT: break
            t0=time.monotonic()
            record={"sample":sample,"run_id":row["kive_run_id"],
                    "invocation_id":invocation_id,"riva_binary_sha256":binary_sha256,
                    "mode":args.mode,"timestamp":time.time(),"status":"started",
                    "cached_inputs":args.cached_inputs}
            report.write(json.dumps(record)+"\n")
            try:
                fq1,fq2=prepare_reads(row,cached_only=args.cached_inputs)
                idx=build_read_index(fq1,fq2)
                if not idx: raise ValueError("Read index empty; refusing disabled read-support")
                read_length=max(idx, key=lambda n:sum(idx[n].values()))
                # Exact same read support index for both arms; never use reference in assembler.
                folder=RESULTS/sample
                if args.mode in ("baseline","all"):
                    iva=stitch_and_score(original_iva(row),idx,read_length,ref,folder,"iva")
                    baselines[sample]={"metrics":iva,"run_id":row["kive_run_id"],
                                       "hxb2_sha256":reference_hash,
                                       "micall_commit":micall_commit(),
                                       "filter_min_length":MIN_LENGTH,
                                       "read_length":read_length,
                                       "stitcher":"modern MiCall referenceless with read_index"}
                    write_atomic(baseline_path,baselines)
                    record["iva"]=iva
                if args.mode in ("riva","all"):
                    base=baselines.get(sample)
                    if not base or base.get("hxb2_sha256")!=reference_hash:
                        raise ValueError("Missing or mismatched IVA HXB2 baseline; first run --mode baseline")
                    if base.get("micall_commit")!=micall_commit():
                        raise ValueError("MiCall has changed since baseline; regenerate both consistently")
                    out=folder/"riva.fasta"
                    out.parent.mkdir(parents=True,exist_ok=True)
                    t_asm=time.monotonic()
                    proc=subprocess.run([args.riva,"--reads1",str(fq1),"--reads2",str(fq2),
                                         "--output",str(out)], text=True,capture_output=True)
                    record["assembler_seconds"]=round(time.monotonic()-t_asm,2)
                    (folder/"riva.stderr.txt").write_text(proc.stderr[-10000:])
                    if proc.returncode: raise RuntimeError(f"Riva exit {proc.returncode}: {proc.stderr[-300:]}")
                    riva=stitch_and_score(fasta_sequences(out),idx,read_length,ref,folder,"riva")
                    record["riva"]=riva
                    target=base["metrics"]["hxb2_score"]
                    got=riva["hxb2_score"]
                    record["score_fraction"]=(got/target if got is not None and target is not None and target>0 else None)
                    # Explicitly avoid PASS claims for undefined/negative scores and structural cases.
                    record["ordinary_score_threshold_met"]=record["score_fraction"] is not None and record["score_fraction"]>=0.95
                    structural=None
                    if roles[sample] in STRUCTURAL_ROLES:
                        structural=reference_fidelity(folder/"iva.raw.fasta",
                                                      folder/"riva.stitched.fasta")
                        record["structural_check"]=structural
                    ok,problems=accept_sample(roles[sample],base["metrics"],riva,structural)
                    record["alpha_pass"]=ok
                    record["alpha_problems"]=problems
                record["status"]="evaluated"
            except Exception as ex:
                record["status"]="error"
                record["error"]=str(ex)
            record["seconds"]=round(time.monotonic()-t0,2)
            report.write(json.dumps(record,sort_keys=True)+"\n")
            records.append(record)
            print(f"{sample}: {record['status']} in {record['seconds']}s",flush=True)
    print(f"Finished invocation in {time.monotonic()-start:.1f}s; results={current}")
    failures=[r for r in records if r.get("status")!="evaluated" or
              (args.mode!="baseline" and not r.get("alpha_pass",False))]
    if len(records)!=len(manifest):
        print(f"ALPHA FAIL: only {len(records)}/{len(manifest)} selected samples completed")
        return 1
    if failures:
        print(f"ALPHA FAIL: {len(failures)}/{len(records)} samples failed:")
        for r in failures:
            print(f"  {r['sample']}: {r.get('error') or '; '.join(r.get('alpha_problems', []))}")
        return 1
    if args.mode=="baseline":
        print("IVA baseline evaluation succeeded (not an Riva alpha PASS)")
    else:
        print("ALPHA SCORE/FIDELITY GATES PASS for selected samples")
    return 0

if __name__=="__main__":
    try: sys.exit(run())
    except KeyboardInterrupt:
        print("Benchmark interrupted or timed out; already recorded results remain available",file=sys.stderr)
        sys.exit(124)


"""Fail-closed marker-guard helper for remap A/B experiments.

This module intentionally does NOT move or duplicate original read pairs when a
safe per-pair mapping from aggregate Q15 nuc loci to individual remap records is
unavailable. It copies the candidate remap unchanged and reports marker-loss
signals for audit. It never invents molecules, phase, or independent counts.
"""
from collections import Counter, defaultdict
import csv
import hashlib
import shutil
from pathlib import Path


def _load_refs(path):
    with open(path) as f:
        rows=list(csv.DictReader(f))
    return ({r['region']:r['sequence'].upper() for r in rows},
            {r['region']:hashlib.sha256(r['sequence'].upper().encode()).hexdigest() for r in rows})


def _strict_assignments(remap_path, ref_hashes):
    pairs=defaultdict(list)
    with open(remap_path) as f:
        reader=csv.DictReader(f)
        for row in reader:
            flag=int(row['flag'])
            proper=bool(flag&0x1 and flag&0x2) and not bool(flag&(0x4|0x8|0x100|0x800))
            h=ref_hashes.get(row['rname']) if proper else None
            pairs[row['qname']].append((row, flag, h, proper))
    out={}
    for q, obs in pairs.items():
        if any(not v[3] for v in obs): continue
        flags=[v[1] for v in obs]
        if len(flags)!=2 or sum(bool(f&0x40) for f in flags)!=1 or sum(bool(f&0x80) for f in flags)!=1 or flags[0]&0x40==flags[1]&0x40 or obs[0][2]!=obs[1][2]: continue
        out[q]=(obs[0][0]['rname'], obs[0][2])
    return out


def _lost_marker_loci(baseline_nuc, candidate_nuc, floor=10):
    def load(p):
        keyed=defaultdict(Counter)
        with open(p) as f:
            for r in csv.DictReader(f):
                if r.get('q-cutoff')!='15': continue
                key=tuple(r.get(k,'') for k in ('seed','region','q-cutoff','query.nuc.pos','refseq.nuc.pos','genome.pos'))
                for a in 'ACGT': keyed[key][a]+=int(r[a] or 0)
        return keyed
    b=load(baseline_nuc); c=load(candidate_nuc)
    return sum(1 for k in set(b)&set(c) for a in 'ACGT' if b[k][a]>=floor and c[k][a]<floor)


def guarded_project(baseline_dir, candidate_dir, output_remap, floor=10):
    bdir=Path(baseline_dir); cdir=Path(candidate_dir)
    _,bh=_load_refs(bdir/'scratch/remap_conseq.csv')
    _,ch=_load_refs(cdir/'scratch/remap_conseq.csv')
    ba=_strict_assignments(bdir/'scratch/remap.csv', bh)
    ca=_strict_assignments(cdir/'scratch/remap.csv', ch)
    lost=_lost_marker_loci(bdir/'nuc.csv', cdir/'nuc.csv', floor)
    shutil.copy2(cdir/'scratch/remap.csv', output_remap)
    changed=sum(1 for q in set(ba)&set(ca) if ba[q][1]!=ca[q][1])
    return {'reassigned_pairs_in_candidate': changed, 'lost_q15_marker_loci': lost,
            'pairs_restored': 0, 'original_pairs_duplicated': 0,
            'reason': 'no_safe_per_pair_marker_to_nuc_mapping'}

"""Write one private opt-in, byte-exact original-pair remap experiment.

The four caller-supplied input SHA256s are externally pinned. All input files
are verified before/after processing. The only output is a new remap CSV;
original sources, MiCall reference tables and FASTQs remain untouched.
"""
import argparse
import csv
import json
import os
from pathlib import Path

from marker_bearing_pair_guard import load_refs
from sequence_exact_pair_restoration import FIELDS, rows_from_file, project_original_pairs
from snv_q15_sources import verify_source
from original_fastq_identity import verified_source_pairs
from sequence_exact_pair_restoration import (original_pairs,raw_mate_pairs,
                                              same_original_mate)


def source_bound_projection(baseline_remap, baseline_refs, candidate_remap,
                            candidate_refs, output, digests,
                            *, restore_same_reference_drift=False, restore_improper_pairs=False,
                            source_fastqs=None, source_fastq_hashes=None):
    sources=(Path(baseline_remap),Path(baseline_refs),
             Path(candidate_remap),Path(candidate_refs))
    for source, digest in zip(sources,digests):
        verify_source(source,digest)
    target=Path(output).resolve()
    protected = sources + tuple(Path(path) for path in (source_fastqs or ()))
    if any(target == p.resolve() or p.resolve().parent in target.parents
           for p in protected):
        raise ValueError('Original evidence directories cannot contain output')
    baseline=rows_from_file(sources[0])
    candidate=rows_from_file(sources[2])
    original_pairs_from_fastq = None
    if (source_fastqs is None) != (source_fastq_hashes is None):
        raise ValueError('Both original FASTQ paths and trusted hashes required')
    if source_fastqs is not None:
        if len(source_fastqs) != 2 or len(source_fastq_hashes) != 2:
            raise ValueError('Exactly two source FASTQ mates and hashes required')
        source_fastqs = tuple(Path(path) for path in source_fastqs)
        for path,digest in zip(source_fastqs,source_fastq_hashes):
            verify_source(path,digest)
        existing = original_pairs(baseline)
        raw = raw_mate_pairs(candidate)
        strict_candidate = original_pairs(candidate)
        targets = {
            name for name in existing.keys() & raw.keys()
            if name not in strict_candidate or any(
                not same_original_mate(existing[name][i],raw[name][i])
                for i in (1,2))
        }
        if targets:
            original_pairs_from_fastq = verified_source_pairs(
                *source_fastqs,targets)
        else:
            original_pairs_from_fastq = {}
    edited, statistics=project_original_pairs(
        baseline,load_refs(sources[1]),candidate,load_refs(sources[3]),
        restore_same_reference_drift=restore_same_reference_drift,
        restore_improper_pairs=restore_improper_pairs,
        original_fastq_pairs=original_pairs_from_fastq)
    for source,digest in zip(sources,digests):
        verify_source(source,digest)
    if source_fastqs is not None:
        for path,digest in zip(source_fastqs,source_fastq_hashes):
            verify_source(path,digest)
    target.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'w',newline='') as stream:
            writer=csv.DictWriter(stream,FIELDS,lineterminator='\n')
            writer.writeheader()
            writer.writerows(edited)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return {'schema_version':'ivanka.exact_reference_original_pair_replay.v1',
            'experimental_only':True,'original_remap_rows':len(candidate),
            'output_remap_rows':len(edited),
            'provenance_sha256':dict(zip(
                ('baseline_remap','baseline_refs','candidate_remap','candidate_refs'),
                digests)),
            'original_read_names_repeated_or_added':False,
            'restore_same_reference_drift':restore_same_reference_drift,
            'restore_improper_pairs':restore_improper_pairs,
            'original_fastq_source_authenticated':source_fastqs is not None,
            'original_fastq_sha256':list(source_fastq_hashes or ()),
            'original_fastq_identifiers_examined':len(original_pairs_from_fastq or {}),
            'biology_or_molecule_independence_proven':False,
            'full_length_haplotype_phase_inferred':False,
            'micall_consensus_improvement_proven':False,
            'statistics':statistics}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline_remap','baseline_refs','candidate_remap',
                 'candidate_refs','output'):
        parser.add_argument(name,type=Path)
    for name in ('baseline_remap','baseline_refs','candidate_remap',
                 'candidate_refs'):
        parser.add_argument('--sha256-'+name.replace('_','-'),required=True)
    parser.add_argument('--restore-same-reference-drift',action='store_true')
    parser.add_argument('--restore-improper-pairs',action='store_true')
    parser.add_argument('--original-fastq-r1',type=Path)
    parser.add_argument('--original-fastq-r2',type=Path)
    parser.add_argument('--sha256-original-r1')
    parser.add_argument('--sha256-original-r2')
    args=parser.parse_args()
    provenance=(args.original_fastq_r1,args.original_fastq_r2,
                args.sha256_original_r1,args.sha256_original_r2)
    if any(item is not None for item in provenance) and not all(
            item is not None for item in provenance):
        parser.error('Original FASTQ path and SHA256 must be given for BOTH mates')
    names=('baseline_remap','baseline_refs','candidate_remap','candidate_refs')
    hashes=tuple(getattr(args,'sha256_'+key) for key in names)
    result=source_bound_projection(*(getattr(args,name) for name in names),
                                   args.output,hashes,
                                   restore_same_reference_drift=args.restore_same_reference_drift,
                                   restore_improper_pairs=args.restore_improper_pairs,
                                   source_fastqs=((args.original_fastq_r1,args.original_fastq_r2)
                                                 if args.original_fastq_r1 and args.original_fastq_r2 else None),
                                   source_fastq_hashes=((args.sha256_original_r1,args.sha256_original_r2)
                                                       if args.sha256_original_r1 and args.sha256_original_r2 else None))
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=='__main__':
    main()

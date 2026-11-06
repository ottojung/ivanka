"""Source-pinned FASTQ two-locus Q15 bridge diagnostic; never infer phase.

Accepts a single unambiguous template FASTA and original paired FASTQs.
Writes only aggregate allele/link counts to private output, never QNAMEs.
"""
import argparse
import json
import os
from pathlib import Path

from snv_q15_fastq import iter_original_pairs
from snv_q15_sources import verify_source
from source_q15_phase_bridges import direct_source_links
from synthetic_phase_fidelity import fasta_records


def source_bound(reference, read1, read2, positions, hashes, *,
                 max_pairs=10000, min_phred=15):
    paths=(Path(reference),Path(read1),Path(read2))
    if len(hashes)!=3 or type(max_pairs) is not int or not 0 < max_pairs <= 1000000:
        raise ValueError('Three hashes and bounded original read-pair count required')
    for path,digest in zip(paths,hashes):
        verify_source(path,digest)
    records=fasta_records(paths[0])
    if len(records)!=1:
        raise ValueError('Only one pinned locus template FASTA is supported')
    source=direct_source_links(records[0][1],positions,
        iter_original_pairs(paths[1],paths[2],max_pairs=max_pairs),
        min_phred=min_phred)
    for path,digest in zip(paths,hashes):
        verify_source(path,digest)
    return dict(source,source_sha256={
        'reference_fasta':hashes[0],'original_r1_fastq':hashes[1],
        'original_r2_fastq':hashes[2]},
        original_fastq_source_verified_before_and_after=True,
        original_qnames_never_serialized=True,
        source_scan_pair_limit=max_pairs)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference_fasta',type=Path)
    parser.add_argument('original_r1',type=Path)
    parser.add_argument('original_r2',type=Path)
    parser.add_argument('--sha256-reference',required=True)
    parser.add_argument('--sha256-r1',required=True)
    parser.add_argument('--sha256-r2',required=True)
    parser.add_argument('--positions',nargs=2,type=int,required=True)
    parser.add_argument('--max-pairs',type=int,default=10000)
    parser.add_argument('--min-phred',type=int,default=15)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    original=(args.reference_fasta,args.original_r1,args.original_r2)
    output=args.output.resolve()
    if any(output==path.resolve() or path.resolve().parent in output.parents
           for path in original):
        parser.error('Output cannot be placed inside original source directories')
    evidence=source_bound(*original,tuple(args.positions),
        (args.sha256_reference,args.sha256_r1,args.sha256_r2),
        max_pairs=args.max_pairs,min_phred=args.min_phred)
    output.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(evidence,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps({'original_pairs_scanned':evidence['original_pairs_scanned'],
                      'original_pairs_with_both_loci_observed':
                          evidence['original_pairs_with_both_loci_observed'],
                      'report_created':True}))


if __name__=='__main__':
    main()

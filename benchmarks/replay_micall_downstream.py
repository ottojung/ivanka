"""Replay original pinned MiCall sam2aln -> aln2counts, with no remapping.

Run inside the SAME MiCall image as the original S48/S12 cap1000 A/B.
Read all prior original scratch inputs from a read-only mount. Do not
regenerate contigs, mapping, IVA or mutable original source files.
"""
from contextlib import ExitStack
from pathlib import Path
import sys

from micall.core.sam2aln import sam2aln
from micall.core.aln2counts import aln2counts

_INPUTS = ('g2p_aligned_csv','remap_conseq_csv','contigs_csv')
_OUTPUTS = ('nuc_csv','amino_csv','insertions_csv','conseq_csv',
            'failed_align_csv','coverage_summary_csv','conseq_region_csv',
            'amino_detail_csv','nuc_detail_csv','genome_coverage_csv',
            'conseq_all_csv','minimap_hits_csv','alignments_csv',
            'alignments_unmerged_csv','alignments_intermediate_csv',
            'alignments_overall_csv','concordance_csv','concordance_detailed_csv',
            'concordance_seed_csv')


def replay(remap_path, original_scratch, output):
    remap_path=Path(remap_path)
    scratch=Path(original_scratch)
    destination=Path(output)
    if destination.exists():
        raise ValueError('Refusing to reuse an existing result directory')
    if destination == scratch or scratch in destination.parents:
        raise ValueError('Cannot overwrite original MiCall scratch evidence')
    destination.mkdir(parents=True,mode=0o700)
    with ExitStack() as stack:
        remap=stack.enter_context(remap_path.open())
        aln=stack.enter_context((destination/'aligned.csv').open('w'))
        insert=stack.enter_context((destination/'conseq_ins.csv').open('w'))
        failed=stack.enter_context((destination/'failed.csv').open('w'))
        clip=stack.enter_context((destination/'clipping.csv').open('w'))
        sam2aln(remap,aln,insert,failed,clipping_csv=clip)
    with ExitStack() as stack:
        inputs={key:stack.enter_context((scratch/(key.replace('_csv','')+'.csv')).open())
                for key in _INPUTS}
        inputs['aligned_csv']=stack.enter_context((destination/'aligned.csv').open())
        inputs['conseq_ins_csv']=stack.enter_context((destination/'conseq_ins.csv').open())
        inputs['clipping_csv']=stack.enter_context((destination/'clipping.csv').open())
        outputs={key:stack.enter_context((destination/(key.replace('_csv','')+'.csv')).open('w'))
                 for key in _OUTPUTS}
        aln2counts(inputs['aligned_csv'],outputs['nuc_csv'],outputs['amino_csv'],
                   outputs['insertions_csv'],outputs['conseq_csv'],
                   outputs['failed_align_csv'],
                   coverage_summary_csv=outputs['coverage_summary_csv'],
                   clipping_csv=inputs['clipping_csv'],
                   conseq_ins_csv=inputs['conseq_ins_csv'],
                   g2p_aligned_csv=inputs['g2p_aligned_csv'],
                   remap_conseq_csv=inputs['remap_conseq_csv'],
                   conseq_region_csv=outputs['conseq_region_csv'],
                   amino_detail_csv=outputs['amino_detail_csv'],
                   nuc_detail_csv=outputs['nuc_detail_csv'],
                   genome_coverage_csv=outputs['genome_coverage_csv'],
                   contigs_csv=inputs['contigs_csv'],
                   conseq_all_csv=outputs['conseq_all_csv'],
                   minimap_hits_csv=outputs['minimap_hits_csv'],
                   alignments_csv=outputs['alignments_csv'],
                   alignments_unmerged_csv=outputs['alignments_unmerged_csv'],
                   alignments_intermediate_csv=outputs['alignments_intermediate_csv'],
                   alignments_overall_csv=outputs['alignments_overall_csv'],
                   concordance_csv=outputs['concordance_csv'],
                   concordance_detailed_csv=outputs['concordance_detailed_csv'],
                   concordance_seed_csv=outputs['concordance_seed_csv'])
    print('DOWNSTREAM_REPLAY_COMPLETE',destination)


if __name__=='__main__':
    replay(*sys.argv[1:])

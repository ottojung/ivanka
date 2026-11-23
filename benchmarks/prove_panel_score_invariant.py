"""Conservative bound for an unchanged best 33-reference MAX score.

If the original best sequence cannot have disappeared, and every new
sequence is shorter than the original best local-alignment score, then
no new sequence can improve that score (maximum +1 per aligned base).
The pinned panel itself must be identical; this is NOT a new score run.
"""
from collections import Counter


def invariant_from_max_sequences(baseline,candidate,original_best_score):
    if (not baseline or not candidate or
            not isinstance(original_best_score,(int,float)) or
            isinstance(original_best_score,bool) or
            original_best_score <= 0):
        raise ValueError('Valid original reference-panel score required')
    left,right=Counter(baseline),Counter(candidate)
    if any(not isinstance(seq,str) or not seq for seq in left|right):
        raise ValueError('Nonempty MAX consensus sequences required')
    removed=left-right
    added=right-left
    removed_max=max(map(len,removed),default=0)
    added_max=max(map(len,added),default=0)
    invariant=removed_max < original_best_score and added_max <= original_best_score
    return {
        'unchanged_best_provable_by_length_bound':bool(invariant),
        'original_pinned_best_panel_score':original_best_score,
        'baseline_max_sequences_lost_ignoring_labels':sum(removed.values()),
        'candidate_max_sequences_added_ignoring_labels':sum(added.values()),
        'longest_removed_max_sequence':removed_max,
        'longest_added_max_sequence':added_max,
        'reference_panel_must_be_unchanged':True,
        'source_max_and_original_pinned_panel_score_must_be_authenticated':True,
        'alignment_not_rerun':True,
        'original_reads_independent_molecules_proven':False,
    }

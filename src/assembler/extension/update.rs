use super::{
    cycle_cut_keeps_prior_path, encode, record_extension_support, CycleTracker, HashSet, Reads, K,
    MAX_CONTIG_LENGTH,
};

// Updating the extension preserves the complete previously assembled path.
pub(super) enum Outcome {
    Advance(Vec<u8>),
    Stop(Option<Vec<u8>>),
    Reject,
}

/// Register support only after a cycle-safe extension has been constructed.
/// A repeat entirely inside the existing contig cannot truncate its path.
pub(super) fn step(
    seq: &[u8],
    proposal: &super::probe::Probe,
    cycles: &mut CycleTracker,
    reads: &Reads,
    supporting_reads: &mut HashSet<u32>,
) -> Outcome {
    let (right_reads, right_ids) = proposal.right_refs();
    let (left_reads, left_ids) = proposal.left_refs();
    let left = &proposal.left;
    let right = &proposal.right;
    let left_rc = &proposal.left_rc;
    let mut next = Vec::with_capacity(left.len() + seq.len() + right.len());
    next.extend_from_slice(&left);
    next.extend_from_slice(&seq);
    next.extend_from_slice(&right);
    if let Some(cut) = cycles.check(&next, K, encode, !left.is_empty()) {
        if !cycle_cut_keeps_prior_path(cut, left.len(), seq.len()) {
            eprintln!("cycle within existing contig; preserving prior phased path");
            return Outcome::Stop(None);
        }
        eprintln!(
            "extension stopped at repeated 512-nt tract ({} nt retained)",
            cut
        );
        next.truncate(cut);
        return Outcome::Stop(Some(next));
    }
    record_extension_support(&right_reads, &right_ids, &right, supporting_reads);
    record_extension_support(&left_reads, &left_ids, &left_rc, supporting_reads);
    if next.len() > MAX_CONTIG_LENGTH {
        reads
            .overlength_rejections
            .set(reads.overlength_rejections.get() + 1);
        eprintln!("rejecting assembly path exceeding {} nt", MAX_CONTIG_LENGTH);
        return Outcome::Reject;
    }
    Outcome::Advance(next)
}

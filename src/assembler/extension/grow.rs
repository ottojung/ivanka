use super::{probe, trace, update};
use super::{CycleTracker, HashSet, Reads, MAX_CONTIG_LENGTH};

/// Grow a contig from the same paired reads until coverage, length, or
/// cycle constraints stop it. Supporting-read IDs are deduplicated across
/// extension rounds; they are not evidence of independent molecules.
pub(crate) fn extend(
    mut seq: Vec<u8>,
    reads: &Reads,
    min_cov: usize,
    min_ratio: usize,
) -> (Vec<u8>, usize) {
    let mut supporting_reads = HashSet::<u32>::new();
    let (mut right_stalled, mut left_stalled, mut cycles) = (false, false, CycleTracker::new());
    for _ in 0..600 {
        if seq.len() > MAX_CONTIG_LENGTH {
            break;
        }
        let proposal = probe::scan(&seq, reads, right_stalled, left_stalled, min_cov, min_ratio);
        let (right_reads, _) = proposal.right_refs();
        let (left_reads, _) = proposal.left_refs();
        // Once a contig covers every possible read, extending the opposite
        // end cannot change the last read-length bases at a stalled end.
        if seq.len() >= reads.max_read_len {
            right_stalled |= proposal.right.is_empty();
            left_stalled |= proposal.left.is_empty();
        }
        if proposal.right.is_empty() && proposal.left.is_empty() {
            trace::stalled(&seq, right_reads, left_reads);
            // With no extension, the same immutable reads and contig produce
            // the same result next iteration. A second probe is redundant.
            break;
        }
        match update::step(&seq, &proposal, &mut cycles, reads, &mut supporting_reads) {
            update::Outcome::Advance(next) => seq = next,
            update::Outcome::Stop(Some(next)) => {
                seq = next;
                break;
            }
            update::Outcome::Stop(None) => break,
            update::Outcome::Reject => return (Vec::new(), 0),
        }
    }
    (seq, supporting_reads.len())
}

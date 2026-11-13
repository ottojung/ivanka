mod breakpoint;
mod overlap;
mod rotate;
mod seam;
mod support;
#[cfg(test)]
mod test_junction;
#[cfg(test)]
mod test_variable;
#[cfg(test)]
mod tests;

use super::{encode, Reads, K};
const MAX_OVERLAP: usize = 512;
const MIN_OVERLAP: usize = 256;

/// Reopen a repeated closed path where original reads reject one adjacency.
pub(super) fn repair(sequence: &[u8], depth: &[u32], reads: &Reads) -> Option<(Vec<u8>, Vec<u32>)> {
    if sequence.len() < 2 * MAX_OVERLAP + 2500
        || depth.len() != sequence.len() - K + 1
        || reads.max_read_len < support::SPAN
    {
        return None;
    }
    let overlap = overlap::length(sequence, MIN_OVERLAP, MAX_OVERLAP)?;
    let core = &sequence[..sequence.len() - overlap];
    if !seam::supported(core, |word| support::present(word, reads)) {
        return None;
    }
    let cut = breakpoint::locate(core, |word| support::present(word, reads))?;
    rotate::at(sequence, depth, cut, overlap, K)
}

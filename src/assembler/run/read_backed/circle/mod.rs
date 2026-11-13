mod breakpoint;
mod rotate;
mod support;
#[cfg(test)]
mod tests;

use super::{encode, Reads, K};
const OVERLAP: usize = 512;

/// Reopen a repeated closed path where original reads reject one adjacency.
pub(super) fn repair(sequence: &[u8], depth: &[u32], reads: &Reads) -> Option<(Vec<u8>, Vec<u32>)> {
    if sequence.len() < 2 * OVERLAP + 2500
        || sequence[..OVERLAP] != sequence[sequence.len() - OVERLAP..]
        || depth.len() != sequence.len() - K + 1
        || reads.max_read_len < support::SPAN
    {
        return None;
    }
    let core = &sequence[..sequence.len() - OVERLAP];
    let cut = breakpoint::locate(core, |word| support::present(word, reads))?;
    rotate::at(sequence, depth, cut, OVERLAP, K)
}

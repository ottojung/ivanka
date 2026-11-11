use super::cycle::{cycle_end, CYCLE_MATCH};
pub(super) fn encode(seq: &[u8]) -> Option<u64> {
    if seq.len() != 31 {
        return None;
    }
    let mut n = 0u64;
    for b in seq {
        let d = match b {
            b'A' => 0,
            b'C' => 1,
            b'G' => 2,
            b'T' => 3,
            _ => return None,
        };
        n = (n << 2) | d;
    }
    Some(n)
}

use super::cycle;
mod oracle;
mod stopping;

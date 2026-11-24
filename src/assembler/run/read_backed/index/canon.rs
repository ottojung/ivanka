use super::K;
const MASK: u64 = (1u64 << (2 * K)) - 1;

/// Pack one fully unambiguous K-window into its canonical 2-bit identity.
pub(crate) fn pack(window: &[u8]) -> Option<u64> {
    if window.len() != K {
        return None;
    }
    let (mut fwd, mut rev) = (0u64, 0u64);
    for &base in window {
        let digit = match base {
            b'A' => 0,
            b'C' => 1,
            b'G' => 2,
            b'T' => 3,
            _ => return None,
        };
        fwd = ((fwd << 2) & MASK) | digit;
        rev = (rev >> 2) | ((3 - digit) << (2 * (K - 1)));
    }
    Some(fwd.min(rev))
}

/// Rolling canonical identities with original start positions. An ambiguous
/// base resets both strands, so no emitted identity spans it.
pub(crate) fn rolling(seq: &[u8]) -> impl Iterator<Item = (usize, u64)> + '_ {
    let (mut fwd, mut rev, mut valid) = (0u64, 0u64, 0usize);
    seq.iter().enumerate().filter_map(move |(i, &base)| {
        let digit = match base {
            b'A' => 0u64,
            b'C' => 1,
            b'G' => 2,
            b'T' => 3,
            _ => {
                (fwd, rev, valid) = (0, 0, 0);
                return None;
            }
        };
        fwd = ((fwd << 2) & MASK) | digit;
        rev = (rev >> 2) | ((3 - digit) << (2 * (K - 1)));
        valid += 1;
        (valid >= K).then(|| (i + 1 - K, fwd.min(rev)))
    })
}

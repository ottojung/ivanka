use super::K;
/// Streams orientation-independent 31-mer identities without storing windows.
/// An ambiguous base resets both strands, so no emitted k-mer spans it.
pub(crate) fn rolling_canonical_kmers(seq: &[u8]) -> impl Iterator<Item = u64> + '_ {
    let (mut forward, mut reverse, mut valid) = (0u64, 0u64, 0usize);
    seq.iter().filter_map(move |&b| {
        let d = match b {
            b'A' => 0u64,
            b'C' => 1,
            b'G' => 2,
            b'T' => 3,
            _ => {
                forward = 0;
                reverse = 0;
                valid = 0;
                return None;
            }
        };
        forward = ((forward << 2) & ((1u64 << (2 * K)) - 1)) | d;
        reverse = (reverse >> 2) | ((3 - d) << (2 * (K - 1)));
        valid += 1;
        (valid >= K).then_some(forward.min(reverse))
    })
}

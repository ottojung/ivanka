// Shift two-bit anchors when bases are unambiguous.
pub(crate) fn next_anchor(
    seq: &[u8],
    i: usize,
    k: usize,
    previous: Option<u64>,
    encode: fn(&[u8]) -> Option<u64>,
) -> Option<u64> {
    if k == 31 && i > 0 {
        if let Some(prev) = previous {
            let digit = match seq[i + k - 1] {
                b'A' => Some(0),
                b'C' => Some(1),
                b'G' => Some(2),
                b'T' => Some(3),
                _ => None,
            };
            if let Some(d) = digit {
                return Some(((prev << 2) & ((1u64 << 62) - 1)) | d);
            }
        }
    }
    encode(&seq[i..i + k])
}

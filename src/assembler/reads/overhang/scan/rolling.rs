use super::{encode, K};
pub(crate) fn rolling_query(seq: &[u8], q: usize, previous: Option<u64>) -> Option<u64> {
    if let Some(p) = previous {
        let d = match seq[q + K - 1] {
            b'A' => Some(0),
            b'C' => Some(1),
            b'G' => Some(2),
            b'T' => Some(3),
            _ => None,
        };
        if let Some(d) = d {
            return Some(((p << 2) & ((1u64 << 62) - 1)) | d);
        }
    }
    encode(&seq[q..q + K])
}

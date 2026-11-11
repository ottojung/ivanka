use super::K;

// A read contributes only when its full overlap is exact and leaves a suffix.
pub(super) fn matching_suffix<'a>(
    contig: &[u8],
    read: &'a [u8],
    q: usize,
    pos: usize,
) -> Option<&'a [u8]> {
    let (begin, read_start) = if q >= pos { (q - pos, 0) } else { (0, pos - q) };
    let overlap = contig.len() - begin;
    if overlap < K || read_start + overlap >= read.len() {
        return None;
    }
    if read[read_start..read_start + overlap] != contig[begin..] {
        return None;
    }
    Some(&read[read_start + overlap..])
}

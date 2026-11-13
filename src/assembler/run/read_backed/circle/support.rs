use super::{encode, Reads, K};
pub(super) const SPAN: usize = 125;

/// A sampled original read must cover the *whole* long window.
pub(super) fn present(window: &[u8], reads: &Reads) -> bool {
    if window.len() != SPAN {
        return false;
    }
    // Twelve consecutive anchors cover every phase of the read index.
    for offset in 48..60 {
        let Some(anchor) = encode(&window[offset..offset + K]) else {
            continue;
        };
        let Some(hits) = reads.index.get(&anchor) else {
            continue;
        };
        for hit in hits {
            let Some(start) = usize::from(hit.pos).checked_sub(offset) else {
                continue;
            };
            if reads.seqs[hit.read as usize].get(start..start + SPAN) == Some(window) {
                return true;
            }
        }
    }
    false
}

use super::Entry;
use super::K;

/// Keep every core base in order and extend each tile by 512 downstream bases.
pub(super) fn partition(header: &str, sequence: &[u8], depth: &[u32]) -> Vec<Entry> {
    const SPAN: usize = 2000;
    const OVERLAP: usize = 512;
    let intact = || vec![(header.to_owned(), sequence.to_vec())];
    let len = sequence.len();
    if len <= SPAN || uniformly_supported(depth) {
        return intact();
    }
    let count = len.div_ceil(SPAN);
    if len / count < 3 * SPAN / 5 || count > 32 {
        return intact();
    }
    let (base, extra) = (len / count, len % count);
    let mut start = 0;
    let mut parts = Vec::with_capacity(count);
    for i in 0..count {
        let width = base + usize::from(i < extra);
        let end = start + width;
        let tile_end = (end + OVERLAP).min(len);
        let positions = &depth[start..tile_end - K + 1];
        if positions.is_empty()
            || positions.iter().filter(|&&v| v >= 3).count() * 5 < positions.len() * 4
        {
            return intact();
        }
        parts.push((
            format!("{header}_tile{}", i + 1),
            sequence[start..tile_end].to_vec(),
        ));
        start = end;
    }
    parts
}

/// A continuous read-supported source contig is a stronger assembly result
/// than any of its overlapping presentation tiles. Require both broad and
/// uninterrupted original-pair evidence before withholding tiling.
fn uniformly_supported(depth: &[u32]) -> bool {
    !depth.is_empty()
        && depth.iter().filter(|&&count| count >= 3).count() * 100 >= depth.len() * 95
        && depth.split(|&count| count >= 3).all(|gap| gap.len() < 100)
}

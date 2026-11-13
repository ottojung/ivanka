/// Retain original exact k-mer depths while linearizing an overlapped cycle.
pub(super) fn at(
    sequence: &[u8],
    depth: &[u32],
    cut: usize,
    overlap: usize,
    k: usize,
) -> Option<(Vec<u8>, Vec<u32>)> {
    let size = sequence.len().checked_sub(overlap)?;
    if cut >= size || size < k || depth.len() != sequence.len() - k + 1 {
        return None;
    }
    let mut linear = Vec::with_capacity(size);
    linear.extend_from_slice(&sequence[cut..size]);
    linear.extend_from_slice(&sequence[..cut]);
    let mut depths = Vec::with_capacity(size - k + 1);
    for position in 0..=size - k {
        let origin = cut + position;
        let origin = if origin <= sequence.len() - k {
            origin
        } else {
            origin - size
        };
        if sequence.get(origin..origin + k) != linear.get(position..position + k) {
            return None;
        }
        depths.push(*depth.get(origin)?);
    }
    Some((linear, depths))
}

use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

pub(super) fn signature(first: &[u8], second: &[u8]) -> u64 {
    let mut hasher = DefaultHasher::new();
    first.hash(&mut hasher);
    0xffu8.hash(&mut hasher);
    second.hash(&mut hasher);
    hasher.finish()
}

pub(super) fn note_exclusive(
    ranges: &mut [Vec<(u32, u32, u32)>],
    candidate: usize,
    pair: usize,
    loci: &std::collections::HashSet<usize>,
) {
    let (mut min, mut max) = (u32::MAX, 0u32);
    for &locus in loci {
        min = min.min(locus as u32);
        max = max.max(locus as u32);
    }
    ranges[candidate].push((pair as u32, min, max));
}

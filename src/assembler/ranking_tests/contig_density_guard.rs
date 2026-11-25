use super::*;
use std::collections::HashMap;

fn path(seed: u64, len: usize) -> Vec<u8> {
    let mut x = seed;
    (0..len)
        .map(|_| {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            b"ACGT"[(x & 3) as usize]
        })
        .collect()
}

// Fail-closed: a short length-matched neighbour is below the SNV audit's
// 128 nt minimum, so suppression would destroy a true haplotype with no
// unphased evidence channel. It must survive even at high read support.
#[test]
fn short_unauditable_single_snv_neighbour_is_kept() {
    let major = path(0x1234_5678_9abc_def0, 96);
    let mut minor = major.clone();
    minor[48] = if minor[48] == b'A' { b'C' } else { b'A' };
    let sampled: HashMap<u64, u32> = HashMap::new();
    let (kept, audit) = select_supported_contigs_with_kmers(
        vec![major, minor.clone()],
        vec![300, 280],
        16,
        0,
        &sampled,
    );
    assert_eq!(kept.len(), 2, "un-auditable short haplotype was suppressed");
    assert!(kept.contains(&minor));
    assert!(audit.is_empty());
}

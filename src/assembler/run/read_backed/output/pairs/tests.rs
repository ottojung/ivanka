use super::{merge, observed};

pub(super) fn sequence(mut seed: u32, n: usize) -> Vec<u8> {
    (0..n)
        .map(|_| {
            seed ^= seed << 13;
            seed ^= seed >> 17;
            seed ^= seed << 5;
            b"ACGT"[(seed as usize) & 3]
        })
        .collect()
}

pub(super) fn append(reads: &mut Vec<Vec<u8>>, fragment: &[u8]) {
    let rc = crate::assembler::reads::rc;
    let r1 = fragment[..150].to_vec();
    let r2 = rc(&fragment[fragment.len() - 150..]);
    reads.extend([r1.clone(), rc(&r1), r2.clone(), rc(&r2)]);
}

#[test]
fn reconstructs_only_the_overlap_observed_between_mates() {
    let original = sequence(16, 270);
    let overlap = merge::insert(&original[..150], &original[120..]).unwrap();
    assert_eq!(overlap, original);
    assert!(merge::insert(&original[..150], &sequence(31, 150)).is_none());
}

#[test]
fn retains_three_independently_observed_paired_fragments() {
    let mut reads = Vec::new();
    for seed in [17, 29, 41] {
        let fragment = sequence(seed, 270);
        for _ in 0..15 {
            append(&mut reads, &fragment);
        }
    }
    let observed = observed(&reads, &[]);
    assert_eq!(observed.len(), 3);
    assert!(observed.iter().all(|(_, sequence)| sequence.len() == 270));
}

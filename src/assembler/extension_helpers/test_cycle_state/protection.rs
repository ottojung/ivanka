use super::*;

#[test]
fn cycle_inside_long_seed_must_not_erase_existing_phased_suffix() {
    let mut state = 0x1234_5678_9abc_def0u64;
    let mut seed = (0..5000)
        .map(|_| {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            b"ACGT"[(state & 3) as usize]
        })
        .collect::<Vec<_>>();
    let motif = seed[100..612].to_vec();
    seed[3000..3512].copy_from_slice(&motif);
    let mut next = seed.clone();
    next.extend_from_slice(b"ACGT");
    let cut = CycleTracker::new().check(&next, 31, encode, false).unwrap();
    assert!(
        cut < seed.len(),
        "the repeat is wholly inside the prior path"
    );
    assert!(!cycle_cut_keeps_prior_path(cut, 0, seed.len()));
    assert!(!cycle_cut_keeps_prior_path(cut, 80, seed.len()));
    assert!(cycle_cut_keeps_prior_path(seed.len() + 80, 80, seed.len()));
}

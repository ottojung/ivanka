use super::{alternative::dna, ambiguous_tail};

#[test]
fn divergent_but_originally_observed_short_branch_is_uncertain() {
    let first = dna(9400);
    let mut tail = first[..932].to_vec();
    for offset in (400..932).step_by(10) {
        tail[offset] = b"ACGT"[(tail[offset] as usize + 1) % 4];
    }
    let mut sequence = first.clone();
    sequence.extend(tail);
    let mut depth = vec![7; sequence.len() - 30];
    assert!(ambiguous_tail(&sequence, &depth, 31));
    depth[1300..6800].fill(0);
    assert!(!ambiguous_tail(&sequence, &depth, 31));
    sequence.truncate(first.len());
    sequence.extend_from_slice(&first[..932]);
    assert!(!ambiguous_tail(
        &sequence,
        &vec![7; sequence.len() - 30],
        31
    ));
}

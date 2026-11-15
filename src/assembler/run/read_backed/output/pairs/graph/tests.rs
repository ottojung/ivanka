use super::chains;

fn sequence(mut seed: u32, n: usize) -> Vec<u8> {
    (0..n)
        .map(|_| {
            seed ^= seed << 13;
            seed ^= seed >> 17;
            seed ^= seed << 5;
            b"ACGT"[(seed as usize) & 3]
        })
        .collect()
}

#[test]
fn joins_only_unambiguous_exactly_overlapping_fragments() {
    let first = sequence(3, 270);
    let mut second = first[180..].to_vec();
    second.extend(sequence(7, 180));
    let mut third = second[180..].to_vec();
    third.extend(sequence(11, 180));
    let inputs = vec![(first, 100), (second, 95), (third, 92)];
    let (paths, included) = chains(&inputs);
    assert!(paths.iter().any(|(seq, _)| seq.len() == 630));
    assert_eq!(included.len(), 3);
}

#[test]
fn refuses_an_equal_overlap_branch_without_molecular_evidence() {
    let first = sequence(17, 270);
    let mut left = first[180..].to_vec();
    let mut right = left.clone();
    left.extend(sequence(29, 180));
    right.extend(sequence(41, 180));
    let (paths, included) = chains(&[(first, 100), (left, 100), (right, 100)]);
    assert!(paths.is_empty());
    assert!(included.is_empty());
}

#[test]
fn never_joins_unrelated_fragments() {
    let parts = [3, 7, 11, 17].map(|seed| (sequence(seed, 270), 100));
    assert!(chains(&parts).0.is_empty());
}

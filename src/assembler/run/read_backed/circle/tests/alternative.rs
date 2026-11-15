use super::alternative_tail_cut;

pub(super) fn dna(size: usize) -> Vec<u8> {
    let mut state = 782_013_417_u64;
    (0..size)
        .map(|_| {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            b"ACGT"[(state % 4) as usize]
        })
        .collect()
}

fn split_example() -> Vec<u8> {
    let first = dna(9400);
    let mut other = first[..5200].to_vec();
    for p in (0..4700).step_by(10) {
        other[p] = b"ACGT"[(other[p] as usize + 1) % 4];
    }
    let mut joined = first;
    joined.extend(other);
    joined
}

#[test]
fn divergent_internal_copy_preserves_two_observed_paths() {
    let sequence = split_example();
    let depths = vec![7; sequence.len() - 30];
    assert_eq!(alternative_tail_cut(&sequence, &depths, 31), Some(9400));
}

#[test]
fn duplicated_tandem_or_missing_support_does_not_claim_a_split() {
    let first = dna(9400);
    let mut intact = first.clone();
    intact.extend_from_slice(&first[..5200]);
    let mut depths = vec![7; intact.len() - 30];
    assert_eq!(alternative_tail_cut(&intact, &depths, 31), None);
    let varied = split_example();
    depths[1000..5500].fill(0);
    assert_eq!(alternative_tail_cut(&varied, &depths, 31), None);
}

#[test]
fn incomplete_or_unrelated_terminal_sequence_is_not_split() {
    let first = dna(9400);
    let mut unrelated = first;
    unrelated.extend_from_slice(&dna(5200));
    let depths = vec![7; unrelated.len() - 30];
    assert_eq!(alternative_tail_cut(&unrelated, &depths, 31), None);
    assert_eq!(alternative_tail_cut(&unrelated, &[], 31), None);
}

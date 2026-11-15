use super::{
    observed,
    tests::{append, sequence},
};

#[test]
fn rejects_sparse_duplicate_or_single_mate_fragments() {
    let mut reads = Vec::new();
    for seed in 1..=50 {
        append(&mut reads, &sequence(seed, 270));
    }
    assert!(observed(&reads, &[]).is_empty());
}

#[test]
fn does_not_duplicate_an_existing_contiguous_contig() {
    let mut reads = Vec::new();
    let fragment = sequence(29, 270);
    for _ in 0..20 {
        append(&mut reads, &fragment);
    }
    for seed in [17, 41] {
        let f = sequence(seed, 270);
        for _ in 0..20 {
            append(&mut reads, &f);
        }
    }
    let existing = vec![(">main".to_string(), fragment)];
    assert_eq!(observed(&reads, &existing).len(), 2);
}

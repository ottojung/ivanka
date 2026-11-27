use super::{qualifies, Statistics};

const LEN: usize = 4000;
const POS: usize = LEN - 30;

fn branch(blocks: &[(usize, usize)]) -> Vec<Vec<u8>> {
    let mut alt = vec![b'A'; LEN];
    for &(start, end) in blocks {
        alt[start..end].fill(b'C');
    }
    vec![vec![b'A'; LEN], alt]
}

fn stats(primary: u32, alt: u32, primary_pairs: usize, alt_pairs: usize) -> Statistics {
    Statistics {
        depth: vec![vec![primary; POS], vec![alt; POS]],
        pairs: vec![primary_pairs, alt_pairs],
        coverage: vec![POS; 2],
        pair_masks: Vec::new(),
    }
}

fn ok(blocks: &[(usize, usize)], evidence: &Statistics) -> bool {
    qualifies(&branch(blocks), evidence, 1, 0, 1)
}

#[test]
fn co_abundant_phased_second_haplotype_qualifies() {
    let evidence = stats(60, 60, 5000, 5000);
    assert!(ok(&[(1000, 1400), (2200, 2600)], &evidence));
}

#[test]
fn minority_depth_or_pair_support_is_not_co_abundant() {
    let evidence = stats(60, 25, 5000, 5000);
    assert!(!ok(&[(1000, 1400), (2200, 2600)], &evidence));
    let evidence = stats(60, 60, 5000, 2000);
    assert!(!ok(&[(1000, 1400), (2200, 2600)], &evidence));
}

#[test]
fn single_substitution_is_not_a_phased_branch() {
    let evidence = stats(60, 60, 5000, 5000);
    assert!(!ok(&[(1000, 1001)], &evidence));
}

#[test]
fn duplicate_contigs_are_not_bounded_branches() {
    let evidence = stats(60, 60, 5000, 5000);
    assert!(!ok(&[], &evidence));
    assert!(!ok(&[(0, LEN)], &evidence));
}

#[test]
fn deeper_private_superposition_is_not_one_phase() {
    let evidence = stats(60, 110, 5000, 5000);
    assert!(!ok(&[(1000, 1400), (2200, 2600)], &evidence));
}

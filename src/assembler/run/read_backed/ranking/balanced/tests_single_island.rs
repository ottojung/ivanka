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

fn stats(primary: u32, alt: u32) -> Statistics {
    Statistics {
        depth: vec![vec![primary; POS], vec![alt; POS]],
        pairs: vec![5000, 5000],
        coverage: vec![POS; 2],
        pair_masks: Vec::new(),
        spans: Vec::new(),
    }
}

fn ok(blocks: &[(usize, usize)], evidence: &Statistics) -> bool {
    qualifies(&branch(blocks), evidence, 1, 0, 1)
}

#[test]
fn one_long_internal_recombinant_island_qualifies() {
    assert!(ok(&[(1000, 1800)], &stats(60, 60)));
}

#[test]
fn terminal_tail_is_not_an_independent_phase() {
    assert!(!ok(&[(0, 800)], &stats(60, 60)));
}

#[test]
fn whole_duplicate_is_not_a_phased_branch() {
    assert!(!ok(&[(0, LEN)], &stats(60, 60)));
}

#[test]
fn minority_and_superposition_are_still_rejected() {
    assert!(!ok(&[(1000, 1800)], &stats(60, 25)));
    assert!(!ok(&[(1000, 1800)], &stats(60, 110)));
}

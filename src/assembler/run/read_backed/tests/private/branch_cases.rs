use super::{ranking, Statistics};

fn stats(masks: Vec<u16>, coverage: Vec<usize>) -> Statistics {
    let pairs = (0..coverage.len())
        .map(|i| masks.iter().filter(|&&m| m & (1 << i) != 0).count())
        .collect();
    Statistics {
        depth: vec![],
        pairs,
        coverage,
        pair_masks: masks,
        spans: vec![],
    }
}

fn primary() -> Vec<u8> {
    vec![b'A'; 4000]
}

fn branch(private_bases: usize) -> Vec<u8> {
    let mut seq = vec![b'A'; 4000 - private_bases];
    seq.extend(vec![b'G'; private_bases]);
    seq
}

#[test]
fn bounded_private_branch_with_shared_pairs_is_retained() {
    let evidence = stats([vec![3; 700], vec![2; 300]].concat(), vec![3970, 3970]);
    assert_eq!(
        ranking::additional(&[primary(), branch(1000)], &evidence, 0),
        vec![1]
    );
}

#[test]
fn wholly_distinct_branch_is_left_to_the_strict_rule() {
    let evidence = stats([vec![3; 700], vec![2; 300]].concat(), vec![3970, 3970]);
    assert!(ranking::additional(&[primary(), branch(4000)], &evidence, 0).is_empty());
}

#[test]
fn tiny_private_branch_is_not_retained() {
    let evidence = stats([vec![3; 700], vec![2; 300]].concat(), vec![3970, 3970]);
    assert!(ranking::additional(&[primary(), branch(100)], &evidence, 0).is_empty());
}

#[test]
fn sparse_private_branch_is_not_retained() {
    let evidence = stats([vec![3; 700], vec![2; 300]].concat(), vec![3970, 1000]);
    assert!(ranking::additional(&[primary(), branch(1000)], &evidence, 0).is_empty());
}

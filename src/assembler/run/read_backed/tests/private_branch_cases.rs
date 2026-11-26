use super::{branch, primary, private_depth, private_stats, ranking, scoring::Statistics};

fn case(bases: usize, coverage: usize) -> (Vec<Vec<u8>>, Statistics) {
    let branch = branch(bases);
    let depth = vec![
        private_depth(&primary(), true),
        private_depth(&branch, true),
    ];
    (
        vec![primary(), branch],
        private_stats(vec![3970, coverage], depth),
    )
}

#[test]
fn bounded_private_branch_with_shared_pairs_is_retained() {
    let (contigs, evidence) = case(1000, 3970);
    assert_eq!(ranking::additional(&contigs, &evidence, 0), vec![1]);
}

#[test]
fn wholly_distinct_branch_is_left_to_the_strict_rule() {
    let (contigs, evidence) = case(4000, 3970);
    assert!(ranking::additional(&contigs, &evidence, 0).is_empty());
}

#[test]
fn tiny_private_branch_is_not_retained() {
    let (contigs, evidence) = case(100, 3970);
    assert!(ranking::additional(&contigs, &evidence, 0).is_empty());
}

#[test]
fn sparse_private_branch_is_not_retained() {
    let (contigs, evidence) = case(1000, 1000);
    assert!(ranking::additional(&contigs, &evidence, 0).is_empty());
}

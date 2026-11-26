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

#[test]
fn additional_prefers_novel_read_support_over_shared_votes() {
    let mut first = vec![b'A'; 2500];
    first.extend(vec![b'G'; 1500]);
    let mut second = vec![b'A'; 3200];
    second.extend(vec![b'C'; 800]);
    let mut partial = vec![0u32; 3970];
    partial[3470..].fill(3);
    let evidence = Statistics {
        depth: vec![vec![3; 3970], partial, vec![3; 3970]],
        pairs: vec![1000, 700, 300],
        coverage: vec![3970; 3],
        pair_masks: [vec![3u16; 700], vec![1; 300]].concat(),
        spans: vec![vec![]; 3],
    };
    let chosen = ranking::additional(&[primary(), first, second], &evidence, 0);
    assert_eq!(chosen.first(), Some(&2));
}

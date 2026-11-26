use super::{branch, primary, private_depth, private_stats, ranking, reverse};

#[test]
fn unsupported_private_tail_is_not_retained() {
    let branch = branch(1000);
    let evidence = private_stats(
        vec![3970, 3970],
        vec![
            private_depth(&primary(), true),
            private_depth(&branch, false),
        ],
    );
    assert!(ranking::additional(&[primary(), branch], &evidence, 0).is_empty());
}

#[test]
fn reverse_complement_private_branch_is_retained() {
    let branch = reverse(&branch(1000));
    let evidence = private_stats(
        vec![3970, 3970],
        vec![
            private_depth(&primary(), true),
            private_depth(&branch, true),
        ],
    );
    assert_eq!(
        ranking::additional(&[primary(), branch], &evidence, 0),
        vec![1]
    );
}

#[test]
fn reverse_complement_of_a_shared_repeat_has_no_private_evidence() {
    let motif: Vec<u8> = (0..4000).map(|i| b"ACGT"[i % 4]).collect();
    let shared = reverse(&motif);
    let evidence = private_stats(
        vec![3970, 3970],
        vec![private_depth(&motif, true), private_depth(&shared, true)],
    );
    assert!(ranking::additional(&[motif, shared], &evidence, 0).is_empty());
}

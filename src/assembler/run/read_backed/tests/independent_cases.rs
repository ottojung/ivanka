use super::{ranking, scoring::Statistics};

fn stats(masks: Vec<u16>, coverage: Vec<usize>) -> Statistics {
    let pairs = (0..coverage.len())
        .map(|i| masks.iter().filter(|&&m| m & (1 << i) != 0).count())
        .collect();
    let spans = vec![vec![]; coverage.len()];
    Statistics {
        depth: vec![],
        pairs,
        coverage,
        pair_masks: masks,
        spans,
        ..Statistics::blank(coverage.len())
    }
}

#[test]
fn independent_short_component_survives_long_primary() {
    let contigs = vec![vec![b'A'; 9600], vec![b'C'; 550]];
    let evidence = stats([vec![1; 700], vec![2; 300]].concat(), vec![9570, 520]);
    assert_eq!(ranking::best(&contigs, &evidence), 0);
    assert_eq!(ranking::additional(&contigs, &evidence, 0), vec![1]);
}

#[test]
fn shared_fragments_cannot_support_duplicate_components() {
    let contigs = vec![vec![b'A'; 9600], vec![b'C'; 550], vec![b'G'; 550]];
    let evidence = stats([vec![1; 700], vec![6; 300]].concat(), vec![9570, 520, 520]);
    assert_eq!(ranking::additional(&contigs, &evidence, 0), vec![1]);
}

#[test]
fn narrow_or_sparse_evidence_does_not_add_components() {
    let contigs = vec![vec![b'A'; 9600], vec![b'C'; 550], vec![b'G'; 550]];
    let evidence = stats(
        [vec![1; 800], vec![2; 50], vec![4; 150]].concat(),
        vec![9570, 520, 150],
    );
    assert!(ranking::additional(&contigs, &evidence, 0).is_empty());
}

#[test]
fn mostly_explained_pairs_do_not_vote_again() {
    let contigs = vec![vec![b'A'; 9600], vec![b'C'; 550]];
    let evidence = stats(
        [vec![3; 650], vec![1; 150], vec![2; 200]].concat(),
        vec![9570, 520],
    );
    assert!(ranking::additional(&contigs, &evidence, 0).is_empty());
}

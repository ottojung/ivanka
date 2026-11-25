use super::{index, paired, ranking, reverse_complement, scoring, sequence};

#[test]
fn opposite_strand_mate_span_is_credited() {
    let contigs = vec![sequence(7, 300), sequence(19, 300)];
    let hits = index::build(&contigs);
    let a = contigs[0][40..85].to_vec();
    let b = reverse_complement(&contigs[0][210..255]);
    let stats = scoring::count(&contigs, &paired(&[(a, b)]), &hits);
    assert_eq!(stats.pairs, vec![1, 0]);
    assert_eq!(stats.concordant, vec![1, 0]);
    assert!(stats.depth[0].iter().any(|&d| d > 0));
}

#[test]
fn same_strand_pair_keeps_depth_but_is_not_linked() {
    let contigs = vec![sequence(29, 300)];
    let hits = index::build(&contigs);
    let a = contigs[0][40..85].to_vec();
    let b = contigs[0][210..255].to_vec();
    let stats = scoring::count(&contigs, &paired(&[(a, b)]), &hits);
    assert_eq!(stats.pairs, vec![1]);
    assert_eq!(stats.concordant, vec![0]);
    assert!(stats.depth[0].iter().any(|&d| d > 0));
}

#[test]
fn links_break_exact_ties_without_overriding_primary_evidence() {
    let contigs = vec![sequence(41, 300), sequence(43, 300)];
    let tie = scoring::Statistics {
        depth: vec![],
        pairs: vec![5, 5],
        coverage: vec![100, 100],
        concordant: vec![0, 1],
    };
    assert_eq!(ranking::best(&contigs, &tie), 1);
    let dominant = scoring::Statistics {
        depth: vec![],
        pairs: vec![6, 4],
        coverage: vec![100, 100],
        concordant: vec![0, 9],
    };
    assert_eq!(ranking::best(&contigs, &dominant), 0);
}

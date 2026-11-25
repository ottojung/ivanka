use super::{index, paired, reverse_complement, scoring, sequence};

#[test]
fn duplicate_placements_do_not_inflate_depth_or_breadth() {
    let mut contig = sequence(11, 120);
    let duplicated = contig[30..90].to_vec();
    contig.extend_from_slice(&sequence(53, 40));
    contig.extend_from_slice(&duplicated);
    contig.extend_from_slice(&sequence(59, 60));
    let contigs = vec![contig];
    let hits = index::build(&contigs);
    let mate = contigs[0][30..75].to_vec();
    let unanchored = sequence(71, 45);
    let stats = scoring::count(&contigs, &paired(&[(mate, unanchored)]), &hits);
    assert_eq!(stats.pairs, vec![1]);
    assert_eq!(stats.concordant, vec![0]);
    assert!(stats.depth[0].iter().all(|&d| d <= 1));
    assert_eq!(stats.coverage, vec![0]);
}

/// Legacy pair counting is preserved: one mate with two loci still supports the contig,
/// but a missing mate cannot be credited as an opposite-strand link.
#[test]
fn short_mates_are_ignored_without_panicking() {
    let contigs = vec![sequence(47, 300)];
    let hits = index::build(&contigs);
    let stats = scoring::count(
        &contigs,
        &paired(&[(vec![b'A'; 5], contigs[0][20..65].to_vec())]),
        &hits,
    );
    assert_eq!(stats.pairs, vec![1]);
    assert_eq!(stats.concordant, vec![0]);
}

#[test]
fn minority_pair_evidence_survives_new_signal() {
    let contigs = vec![sequence(31, 400), sequence(37, 200)];
    let hits = index::build(&contigs);
    let major = (
        contigs[0][40..85].to_vec(),
        reverse_complement(&contigs[0][200..245]),
    );
    let minor = (
        contigs[1][30..75].to_vec(),
        reverse_complement(&contigs[1][120..165]),
    );
    let stats = scoring::count(&contigs, &paired(&[major, minor]), &hits);
    assert_eq!(stats.pairs, vec![1, 1]);
    assert_eq!(stats.concordant, vec![1, 1]);
    assert_eq!(stats.pairs.iter().sum::<usize>(), 2);
    assert!(stats.depth[1].iter().any(|&d| d > 0));
}

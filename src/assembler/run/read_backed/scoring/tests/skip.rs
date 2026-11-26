use super::support::hits;
use super::{count, K};

#[test]
fn single_locus_pairs_are_not_counted() {
    let map = hits(&[(b'A', vec![(0, 0), (0, 1)]), (b'C', vec![(1, 5)])]);
    let contigs = vec![vec![b'A'; K + 4], vec![b'C'; K + 8]];
    let seqs = vec![
        vec![b'A'; K],
        vec![],
        vec![b'A'; K],
        vec![],
        vec![b'C'; K],
        vec![],
        vec![b'C'; K],
        vec![],
        vec![b'A'; K],
        vec![],
        vec![b'A'; K],
        vec![],
    ];
    let stats = count(&contigs, &super::support::reads(seqs), &map);
    assert_eq!(stats.pairs, vec![2, 0]);
    assert_eq!(stats.pair_masks, vec![1, 0, 1]);
    assert_eq!(stats.depth[0][0], 2);
    assert_eq!(stats.depth[0][1], 2);
    assert!(stats.depth[1].iter().all(|&d| d == 0));
    assert_eq!(stats.coverage, vec![0, 0]);
}

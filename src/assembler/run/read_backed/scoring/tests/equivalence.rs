use super::byte_index;
use super::reference;
use super::support::{lcg, reads};
use super::{count, index, K};

#[test]
fn scan_matches_pairwise_hashmap_reference() {
    let mut state = 0x1234_5678_9abc_def0u64;
    let contigs: Vec<Vec<u8>> = (0..3)
        .map(|_| (0..140).map(|_| lcg(&mut state)).collect())
        .collect();
    let map = index::build(&contigs);
    let byte_map = byte_index::build(&contigs);
    let mut seqs = Vec::new();
    for i in 0..240 {
        let source = &contigs[i % contigs.len()];
        let offset = (i * 17) % (source.len() - 40);
        let read: Vec<u8> = source[offset..offset + 40].to_vec();
        seqs.push(read.clone());
        seqs.push(vec![]);
        if i % 9 == 0 {
            seqs.push(read[..K - 1].to_vec());
        } else {
            let mut rc = read;
            rc.reverse();
            seqs.push(rc);
        }
        seqs.push(vec![]);
    }
    let input = reads(seqs);
    let got = count(&contigs, &input, &map);
    let (depth, pairs, coverage, pair_masks) = reference::count(&contigs, &input, &byte_map);
    assert_eq!(got.depth, depth);
    assert_eq!(got.pairs, pairs);
    assert_eq!(got.coverage, coverage);
    assert_eq!(got.pair_masks, pair_masks);
    assert!(got.pairs.iter().any(|&n| n > 0));
    assert!(got.depth.iter().flatten().any(|&d| d == 0));
    assert!(got.depth.iter().flatten().any(|&d| d >= 3));
}

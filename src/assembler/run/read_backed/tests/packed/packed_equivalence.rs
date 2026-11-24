use super::rolling_properties::{lcg, reads};
use super::{byte_index, byte_reference, index, scoring, K};

#[test]
fn packed_pipeline_matches_original_byte_key_pipeline() {
    let mut state = 0x1234_5678_9abc_def0u64;
    let mut contigs: Vec<Vec<u8>> = (0..3)
        .map(|_| {
            (0..420)
                .map(|i| if i % 61 == 0 { b'N' } else { lcg(&mut state) })
                .collect()
        })
        .collect();
    contigs.push(vec![b'A'; 200]);
    let mut seqs = Vec::new();
    for i in 0..160 {
        let source = &contigs[i % contigs.len()];
        let offset = (i * 29) % (source.len() - 80);
        let read = source[offset..offset + 60].to_vec();
        seqs.push(read.clone());
        seqs.push(vec![]);
        if i % 2 == 0 {
            seqs.push(read);
        } else {
            let mut rc = read;
            rc.reverse();
            seqs.push(rc);
        }
        seqs.push(vec![]);
    }
    seqs.extend([vec![b'N'; K + 4], vec![], vec![b'A'; K - 1], vec![]]);
    let input = reads(seqs);
    let packed = scoring::count(&contigs, &input, &index::build(&contigs));
    let (depth, pairs, coverage, masks) =
        byte_reference::count(&contigs, &input, &byte_index::build(&contigs));
    assert_eq!(packed.depth, depth);
    assert_eq!(packed.pairs, pairs);
    assert_eq!(packed.coverage, coverage);
    assert_eq!(packed.pair_masks, masks);
    assert!(packed.pairs.iter().any(|&n| n > 0));
}

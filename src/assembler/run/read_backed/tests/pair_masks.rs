use super::{index, scoring, Reads};

#[test]
fn each_original_fragment_has_one_mask_of_supported_components() {
    let a = b"AGCTTGACCGTACGATCGTTAGACCTGGAATCCGTCAGTAGCTACGCTTCGATGACATCA".to_vec();
    let b = b"CGGATCACCTATGAGATGCTCACGTGTTGTTGAGCGTTTACCTGACATCTGAACGTTGC".to_vec();
    let contigs = vec![a.clone(), b.clone()];
    let reads = Reads {
        seqs: vec![
            a.clone(),
            vec![],
            a.clone(),
            vec![],
            b.clone(),
            vec![],
            b.clone(),
            vec![],
            a,
            vec![],
            b,
            vec![],
        ],
        index: Default::default(),
        seed_counts: Default::default(),
        max_read_len: 60,
        overlength_rejections: Default::default(),
        overhang_cache: Default::default(),
    };
    let evidence = scoring::count(&contigs, &reads, &index::build(&contigs));
    assert_eq!(evidence.pair_masks, vec![1, 2, 3]);
    assert_eq!(evidence.pairs, vec![2, 2]);
}

use super::{index, ranking, scoring};

#[test]
fn breadth_pair_support_beats_short_count_bias() {
    let contigs = vec![vec![b'A'; 1150], vec![b'C'; 440]];
    let stats = scoring::Statistics {
        depth: vec![],
        pairs: vec![410, 578],
        coverage: vec![1116, 420],
    };
    assert_eq!(ranking::best(&contigs, &stats), 0);
}

#[test]
fn narrow_dense_contig_can_beat_long_unsupported_extension() {
    let contigs = vec![vec![b'A'; 5651], vec![b'C'; 4033]];
    let stats = scoring::Statistics {
        depth: vec![],
        pairs: vec![8416, 3191],
        coverage: vec![466, 1220],
    };
    assert_eq!(ranking::best(&contigs, &stats), 1);
}

#[test]
fn repetitive_kmers_cannot_inflate_original_pair_evidence() {
    let hits = index::build(&[vec![b'A'; 1000]]);
    assert!(!hits.contains_key(&[b'A'; 31]));
}

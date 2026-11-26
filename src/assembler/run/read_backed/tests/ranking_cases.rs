use super::{dense_spans, index, ranking, scoring};

fn split_depth() -> Vec<u32> {
    [vec![120; 1200], vec![4; 70], vec![120; 1200]].concat()
}

#[test]
fn breadth_pair_support_beats_short_count_bias() {
    let contigs = vec![vec![b'A'; 1150], vec![b'C'; 440]];
    let stats = scoring::Statistics {
        depth: vec![],
        pair_masks: vec![],
        pairs: vec![410, 578],
        coverage: vec![1116, 420],
        spans: vec![vec![], vec![]],
    };
    assert_eq!(ranking::best(&contigs, &stats), 0);
}

#[test]
fn narrow_dense_contig_can_beat_long_unsupported_extension() {
    let contigs = vec![vec![b'A'; 5651], vec![b'C'; 4033]];
    let stats = scoring::Statistics {
        depth: vec![],
        pair_masks: vec![],
        pairs: vec![8416, 3191],
        coverage: vec![466, 1220],
        spans: vec![vec![], vec![]],
    };
    assert_eq!(ranking::best(&contigs, &stats), 1);
}

#[test]
fn repetitive_kmers_cannot_inflate_original_pair_evidence() {
    let hits = index::build(&[vec![b'A'; 1000]]);
    assert!(!hits.contains_key(&[b'A'; 31]));
}

#[test]
fn graded_or_underexposed_gap_is_not_a_join() {
    let mut graded = split_depth();
    graded[1200..1270].fill(45);
    assert_eq!(ranking::junction(&graded, &dense_spans()), None);
    let mut wide = split_depth();
    wide[1100..1400].fill(4);
    assert_eq!(ranking::junction(&wide, &dense_spans()), None);
}

#[test]
fn clonal_valley_with_broken_flank_is_not_a_join() {
    let mut depth = split_depth();
    depth[300..500].fill(4);
    assert_eq!(ranking::junction(&depth, &dense_spans()), None);
}

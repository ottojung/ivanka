use super::{dense_spans, ranking};

fn split_depth() -> Vec<u32> {
    [vec![120; 1200], vec![4; 70], vec![120; 1200]].concat()
}

#[test]
fn deep_narrow_valley_between_dense_flanks_is_a_join() {
    assert_eq!(
        ranking::junction(&split_depth(), &dense_spans()),
        Some((1200, 1270))
    );
}

#[test]
fn uniform_clonal_contig_has_no_join() {
    assert_eq!(ranking::junction(&vec![120; 5000], &dense_spans()), None);
    assert_eq!(ranking::junction(&vec![3; 5000], &dense_spans()), None);
    assert_eq!(ranking::junction(&vec![120; 1200], &dense_spans()), None);
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

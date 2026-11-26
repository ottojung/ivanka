use super::{dense_spans, ranking};

fn split_depth() -> Vec<u32> {
    [vec![120; 1200], vec![4; 70], vec![120; 1200]].concat()
}

#[test]
fn deep_narrow_valley_without_spanning_fragments_is_a_join() {
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
fn spanning_original_fragments_reject_a_genuine_molecule_split() {
    let mut spans = dense_spans();
    spans.extend(vec![(1100, 1350); 40]);
    assert_eq!(ranking::junction(&split_depth(), &spans), None);
    spans.extend(vec![(1100, 1350); 10]);
    assert_eq!(ranking::junction(&split_depth(), &spans), None);
}

#[test]
fn sparse_spanning_evidence_still_permits_the_join_call() {
    let mut spans = dense_spans();
    spans.extend(vec![(1100, 1350); 5]);
    assert_eq!(
        ranking::junction(&split_depth(), &spans),
        Some((1200, 1270))
    );
}

#[test]
fn missing_cooccurrence_alone_cannot_declare_a_flank_join() {
    // Absence of co-occurring pairs is not linkage: a uniform high-depth
    // contig with no spanning evidence stays whole, never a fabricated join.
    assert_eq!(ranking::junction(&vec![130; 3000], &[]), None);
    assert_eq!(ranking::pieces(None, 3000), vec![(0, 3000)]);
}

#[test]
fn valley_narrower_than_a_kmer_is_not_split() {
    let depth = [vec![120; 1200], vec![4; 10], vec![120; 1200]].concat();
    assert_eq!(ranking::junction(&depth, &dense_spans()), None);
}

#[test]
fn one_mate_inside_the_valley_vetoes_a_false_join() {
    let mut spans = dense_spans();
    spans.extend(vec![(1000, 1220); 40]);
    assert_eq!(ranking::junction(&split_depth(), &spans), None);
}

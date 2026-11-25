use super::{dense_spans, ranking};

fn split_depth() -> Vec<u32> {
    [vec![120; 1200], vec![4; 70], vec![120; 1200]].concat()
}

#[test]
fn unsupported_valley_has_no_original_fragment_spanning_it() {
    assert_eq!(
        ranking::junction(&split_depth(), &dense_spans()),
        Some((1200, 1270))
    );
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

use super::{mate_linked, PairLinks};

#[test]
fn keeps_fragment_cross_linked_by_original_mates() {
    let mut links = PairLinks::new();
    links.insert((0, 3), 3);
    assert!(mate_linked(3, &[0], &links));
    assert!(!mate_linked(1, &[0], &links));
}

#[test]
fn independent_anchored_mates_are_sufficient() {
    let mut links = PairLinks::new();
    links.insert((2, 2), 10);
    assert!(mate_linked(2, &[0], &links));
}

#[test]
fn single_or_ambiguous_mate_is_insufficient() {
    let mut links = PairLinks::new();
    links.insert((0, 1), 1);
    links.insert((1, 0), 1);
    assert!(!mate_linked(1, &[0], &links));
    assert!(!mate_linked(1, &[0], &PairLinks::new()));
}

use super::{anchor, indexed, K};

#[test]
fn two_collinear_separated_windows_anchor_one_contig() {
    let (read, hits) = indexed();
    assert_eq!(anchor(read, &hits), Some(0));
}

#[test]
fn mismatched_offsets_cannot_establish_a_mate_link() {
    let (read, mut hits) = indexed();
    hits.values_mut().last().unwrap()[0].1 += 11;
    assert_eq!(anchor(read, &hits), None);
}

#[test]
fn reverse_collinear_windows_anchor_one_contig() {
    let (read, mut hits) = indexed();
    let keys = [
        read[..K].try_into().unwrap(),
        read[26..26 + K].try_into().unwrap(),
    ];
    hits.insert(keys[0], vec![(0, 54)]);
    hits.insert(keys[1], vec![(0, 28)]);
    assert_eq!(anchor(read, &hits), Some(0));
}

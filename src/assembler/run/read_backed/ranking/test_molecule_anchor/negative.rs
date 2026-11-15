use super::{anchor, indexed, K};

#[test]
fn two_plausible_contigs_are_ambiguous() {
    let (read, mut hits) = indexed();
    for loci in hits.values_mut() {
        loci.push((1, loci[0].1 + 50));
    }
    assert_eq!(anchor(read, &hits), None);
}

#[test]
fn single_spurious_hit_does_not_create_ambiguity() {
    let (read, mut hits) = indexed();
    hits.values_mut().next().unwrap().push((1, 77));
    assert_eq!(anchor(read, &hits), Some(0));
}

#[test]
fn nearby_or_short_windows_cannot_anchor() {
    let (read, mut hits) = indexed();
    hits.clear();
    for pos in [0, 2] {
        let key: [u8; K] = read[pos..pos + K].try_into().unwrap();
        hits.insert(key, vec![(0, 5 + pos)]);
    }
    assert_eq!(anchor(read, &hits), None);
    assert_eq!(anchor(&read[..K - 1], &hits), None);
}

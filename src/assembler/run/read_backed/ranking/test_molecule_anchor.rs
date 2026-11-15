use super::{molecules::anchor, Hits, K};

fn indexed() -> (&'static [u8], Hits) {
    let read = b"ACGTTGACGATTCGAGCTAGTCAGGTACCAGTT";
    let mut hits = Hits::new();
    let first: [u8; K] = read[..K].try_into().unwrap();
    let second: [u8; K] = read[2..2 + K].try_into().unwrap();
    hits.insert(first, vec![(0, 5)]);
    hits.insert(second, vec![(0, 7)]);
    (read, hits)
}

#[test]
fn two_distinct_loci_anchor_one_contig() {
    let (read, hits) = indexed();
    assert_eq!(anchor(read, &hits), Some(0));
}

#[test]
fn two_plausible_contigs_cannot_certify_a_pair() {
    let (read, mut hits) = indexed();
    for loci in hits.values_mut() {
        let pos = loci[0].1;
        loci.push((1, pos + 50));
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
fn one_locus_or_short_read_cannot_anchor() {
    let (read, mut hits) = indexed();
    hits.remove(&read[2..2 + K]);
    assert_eq!(anchor(read, &hits), None);
    assert_eq!(anchor(&read[..K - 1], &hits), None);
}

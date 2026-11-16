use super::{select::complements, selection_fixture::fixture, Hits, K};

/// Test-only forward-locus index; no import outside the sibling module.
fn build(contigs: &[Vec<u8>]) -> Hits {
    let mut index = Hits::new();
    for (candidate, sequence) in contigs.iter().enumerate() {
        for (position, word) in sequence.windows(K).enumerate() {
            index
                .entry(word.try_into().expect("31 bases"))
                .or_default()
                .push((candidate, position));
        }
    }
    index.retain(|_, loci| loci.len() <= 8);
    index
}

#[test]
fn suppresses_competing_alternative_but_retains_disjoint_path() {
    let (contigs, stats, mut links) = fixture();
    let hits = build(&contigs);
    assert!(complements(&contigs, &stats, &hits, 0, &links).is_empty());
    links.remove(&(0, 1));
    links.remove(&(1, 0));
    assert_eq!(complements(&contigs, &stats, &hits, 0, &links), vec![1]);
}

#[test]
fn short_region_complement_survives_strong_cross_anchors() {
    let (mut contigs, mut stats, links) = fixture();
    contigs[1].truncate(400);
    stats.coverage[1] = 400 - K + 1;
    stats.depth[1].truncate(400 - K + 1);
    let hits = build(&contigs);
    assert_eq!(complements(&contigs, &stats, &hits, 0, &links), vec![1]);
}

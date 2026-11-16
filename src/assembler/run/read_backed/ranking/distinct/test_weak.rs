use super::{redundant::weak_alternative, selection_fixture::fixture};

#[test]
fn a_sparse_full_length_alternative_does_not_displace_the_major_path() {
    let (contigs, mut stats, _) = fixture();
    stats.pairs = vec![402, 47];
    stats.coverage = vec![286, 222];
    assert!(weak_alternative(1, 0, &contigs, &stats));
    stats.pairs[1] = 81;
    assert!(!weak_alternative(1, 0, &contigs, &stats));
}

#[test]
fn more_broadly_covered_alternative_remains_eligible() {
    let (contigs, mut stats, _) = fixture();
    stats.pairs = vec![402, 47];
    stats.coverage = vec![286, 287];
    assert!(!weak_alternative(1, 0, &contigs, &stats));
}

#[test]
fn different_length_or_inconclusive_abundance_cannot_trigger_filter() {
    let (mut contigs, mut stats, _) = fixture();
    stats.pairs = vec![402, 47];
    contigs[1].truncate(400);
    assert!(!weak_alternative(1, 0, &contigs, &stats));
    contigs[1] = vec![b'A'; 1_025];
    stats.pairs = vec![29, 3];
    assert!(!weak_alternative(1, 0, &contigs, &stats));
}

use super::{complement_cases::random_sequence, index, ranking, scoring};

fn select(sequences: &[Vec<u8>]) -> Vec<usize> {
    let hits = index::build(sequences);
    let stats = scoring::Statistics {
        depth: sequences.iter().map(|s| vec![4; s.len() - 30]).collect(),
        pairs: vec![50; sequences.len()],
        coverage: sequences.iter().map(|s| s.len() - 30).collect(),
    };
    let links = (0..sequences.len()).map(|i| ((i, i), 3)).collect();
    ranking::complements(sequences, &stats, &hits, 0, &links)
}

#[test]
fn preserves_multiple_independently_supported_islands() {
    let contigs = (1..=5).map(|i| random_sequence(i, 300)).collect::<Vec<_>>();
    assert_eq!(select(&contigs), vec![1, 2, 3, 4]);
}

#[test]
fn excludes_duplicate_paths_after_first_selection() {
    let first = random_sequence(1, 300);
    let other = random_sequence(2, 190);
    let chosen = select(&[first, other.clone(), other]);
    assert_eq!(chosen, vec![1]);
}

#[test]
fn limits_number_of_secondary_components() {
    let contigs = (1..=15)
        .map(|i| random_sequence(i, 300))
        .collect::<Vec<_>>();
    assert_eq!(select(&contigs).len(), 7);
}

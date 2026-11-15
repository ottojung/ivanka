use super::{ranking, scoring};

fn cohort() -> (Vec<Vec<u8>>, scoring::Statistics) {
    let lengths = [10025, 11256, 14724, 9616];
    (
        lengths.iter().map(|&len| vec![b'A'; len]).collect(),
        scoring::Statistics {
            depth: Vec::new(),
            pairs: vec![9513, 9513, 9906, 9394],
            coverage: vec![9989, 11215, 14683, 9571],
        },
    )
}

#[test]
fn coherent_original_pair_path_beats_ambiguous_long_repeated_path() {
    let (contigs, stats) = cohort();
    assert_eq!(ranking::best(&contigs, &stats), 2);
    assert_eq!(ranking::best_coherent(&contigs, &stats, |i| i != 3), 3);
}

#[test]
fn do_not_prefer_an_unsupported_or_absent_coherent_path() {
    let (contigs, mut stats) = cohort();
    stats.pairs[3] = 1000;
    assert_eq!(ranking::best_coherent(&contigs, &stats, |i| i != 3), 2);
    assert_eq!(ranking::best_coherent(&contigs, &stats, |_| true), 2);
}

#[test]
fn unchanged_ranking_when_best_path_is_coherent() {
    let (contigs, stats) = cohort();
    assert_eq!(ranking::best_coherent(&contigs, &stats, |_| false), 2);
}

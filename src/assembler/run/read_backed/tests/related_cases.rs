use super::{ranking, scoring::Statistics};

fn stats(coverage: Vec<usize>, masks: Vec<u16>, exclusive: Vec<u16>) -> Statistics {
    let pairs = (0..coverage.len())
        .map(|i| masks.iter().filter(|&&m| m & (1 << i) != 0).count())
        .collect();
    Statistics {
        depth: vec![],
        pairs,
        coverage,
        pair_masks: masks,
        exclusive_masks: exclusive,
    }
}

fn long_contigs(n: usize) -> Vec<Vec<u8>> {
    (0..n).map(|_| vec![b'A'; 2000]).collect()
}

#[test]
fn related_strain_with_discriminating_pairs_is_added() {
    // Every pair supports both candidates, so ordinary pair masks cannot
    // separate them; the second haplotype is justified by 31-mers that occur
    // in no other candidate.
    let evidence = stats(
        vec![1990, 1990],
        vec![3; 2000],
        [vec![2; 1200], vec![0; 800]].concat(),
    );
    assert_eq!(ranking::additional(&long_contigs(2), &evidence, 0), vec![1]);
}

#[test]
fn clonal_duplicate_without_discriminating_pairs_is_not_added() {
    let evidence = stats(vec![1990, 1990], vec![3; 2000], vec![0; 2000]);
    assert!(ranking::additional(&long_contigs(2), &evidence, 0).is_empty());
}

#[test]
fn shared_discriminating_fragments_cannot_establish_two_phases() {
    // The same discriminating fragments support candidates 1 and 2. After one
    // haplotype consumes them, the other has no independent evidence left.
    let evidence = stats(vec![1990, 1990, 1990], vec![7; 2000], vec![6; 2000]);
    assert_eq!(ranking::additional(&long_contigs(3), &evidence, 0), vec![1]);
}

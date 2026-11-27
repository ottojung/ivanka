use super::{additional, long_contigs, stats};

#[test]
fn related_strain_with_discriminating_pairs_is_added() {
    // Every pair supports both candidates, so ordinary pair masks cannot
    // separate them; the second haplotype is justified by 31-mers that occur
    // in no other candidate. Discriminating pairs are 1200/2000 = 60%.
    let evidence = stats(
        vec![1990, 1990],
        vec![3; 2000],
        [vec![2; 1200], vec![0; 800]].concat(),
    );
    assert_eq!(additional(&long_contigs(2), &evidence, 0), vec![1]);
}

#[test]
fn discriminating_pair_floor_is_ten_percent() {
    // 2000 discriminating pairs set a 200-pair floor. Candidate 1 with 199
    // exclusive pairs fails; with 200 it qualifies. Primary-only exclusive
    // pairs inflate the denominator without voting for the second component.
    let contigs = long_contigs(2);
    let below = stats(
        vec![1990, 1990],
        [vec![3; 200], vec![0; 1800]].concat(),
        [vec![2; 199], vec![1; 1801]].concat(),
    );
    assert!(additional(&contigs, &below, 0).is_empty());
    let at_floor = stats(
        vec![1990, 1990],
        [vec![3; 200], vec![0; 1800]].concat(),
        [vec![2; 200], vec![1; 1800]].concat(),
    );
    assert_eq!(additional(&contigs, &at_floor, 0), vec![1]);
}

#[test]
fn related_selection_is_deterministic_under_ties() {
    // Two equally supported related candidates tie exactly; the declared
    // low-index tie break must be stable across identical read evidence, so
    // repeated assembly of the same inputs produces byte-identical output.
    let contigs = long_contigs(3);
    let evidence = stats(vec![1990, 1990, 1990], vec![7; 2000], vec![6; 2000]);
    let first = additional(&contigs, &evidence, 0);
    let second = additional(&contigs, &evidence, 0);
    assert_eq!(first, second);
    assert_eq!(first, vec![1]);
}

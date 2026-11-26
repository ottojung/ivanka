use super::Accumulator;

#[test]
fn accumulator_deduplicates_within_a_generation_and_resets_between_pairs() {
    let mut accum = Accumulator::new(&[4, 4]);
    accum.begin();
    accum.insert(0, 1);
    accum.insert(0, 1);
    accum.insert(0, 3);
    accum.insert(1, 2);
    let mut seen: Vec<(usize, Vec<usize>)> = Vec::new();
    accum.apply(|c, loci| seen.push((c, loci.to_vec())));
    assert_eq!(seen, vec![(0, vec![1, 3]), (1, vec![2])]);

    // apply() clears the touched locus vectors; touched bits are reset by the
    // next begin() (scan calls exactly one apply per pair).

    accum.begin();
    accum.insert(0, 1);
    let mut next: Vec<(usize, Vec<usize>)> = Vec::new();
    accum.apply(|c, loci| next.push((c, loci.to_vec())));
    assert_eq!(next, vec![(0, vec![1])]);
}

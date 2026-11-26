use super::{reads, repeated_fragment, sequence};

fn retained(contigs: &mut Vec<Vec<u8>>, data: &super::super::Reads, limit: usize) -> usize {
    super::super::retain(contigs, data, limit, None).unwrap()
}

#[test]
fn does_not_add_repeated_observations_as_independent_support() {
    let fragment = sequence(60, 2);
    let mut contigs = vec![sequence(240, 1)];
    let mut data = reads();
    data.seqs.extend(vec![fragment.clone(); 4]);
    assert_eq!(retained(&mut contigs, &data, 16), 0);
}

#[test]
fn skips_regions_already_represented_by_selected_contigs() {
    let fragment = sequence(60, 2);
    let mut joined = sequence(240, 1);
    joined.extend_from_slice(&fragment);
    let mut contigs = vec![joined];
    let mut data = reads();
    data.seqs = repeated_fragment(&fragment, 20);
    assert_eq!(retained(&mut contigs, &data, 16), 0);
}

#[test]
fn ignores_trace_components_below_library_share() {
    let fragment = sequence(60, 2);
    let mut data = reads();
    data.seqs = repeated_fragment(&fragment, 20);
    for n in 0..3000u64 {
        let a = sequence(60, 500 + n);
        let b = sequence(60, 9000 + n);
        data.seqs.extend([a.clone(), a.clone(), b.clone(), b]);
    }
    let mut contigs = vec![sequence(240, 1)];
    assert_eq!(retained(&mut contigs, &data, 16), 0);
}

#[test]
fn respects_the_contig_budget() {
    let fragment = sequence(60, 2);
    let mut data = reads();
    data.seqs = repeated_fragment(&fragment, 20);
    let mut contigs = vec![sequence(240, 1)];
    assert_eq!(retained(&mut contigs, &data, 1), 0);
}

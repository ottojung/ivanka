use super::{
    approximate_fixtures::{diverged, fixture, path},
    approximate_junction,
};

#[test]
fn approximate_repeat_without_spanning_pairs_is_a_join() {
    let first = path(0x1234_5678_9abc_def0, 4000);
    let second = diverged(&first);
    let (seq, depth, spans) = fixture(second, false);
    assert_eq!(
        approximate_junction(&seq, &depth, &spans),
        Some((2000, 5000))
    );
}

#[test]
fn supported_homologous_repeat_is_not_split() {
    let first = path(0x1234_5678_9abc_def0, 4000);
    let second = diverged(&first);
    let (seq, depth, spans) = fixture(second, true);
    assert_eq!(approximate_junction(&seq, &depth, &spans), None);
}

#[test]
fn genuine_tandem_repeat_is_not_split() {
    let unit = path(0x0bad_c0de_dead_beef, 150);
    let mut tandem = Vec::new();
    for _ in 0..30 {
        tandem.extend_from_slice(&unit);
    }
    let (seq, depth, spans) = fixture(tandem, false);
    assert_eq!(approximate_junction(&seq, &depth, &spans), None);
}

#[test]
fn distinct_haplotypes_and_supported_clonal_paths_are_not_split() {
    let third = path(0xdead_beef_1234_5678, 4000);
    let (seq, depth, spans) = fixture(third, false);
    assert_eq!(approximate_junction(&seq, &depth, &spans), None);
    let clonal = path(0x0102_0304_0506_0708, 5000);
    let depth = vec![120u32; clonal.len() - 30];
    assert_eq!(approximate_junction(&clonal, &depth, &[(0, 1400)]), None);
}

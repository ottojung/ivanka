use super::{ranking, Statistics};

fn stats(masks: Vec<u16>, coverage: Vec<usize>) -> Statistics {
    let pairs = (0..coverage.len())
        .map(|i| masks.iter().filter(|&&m| m & (1 << i) != 0).count())
        .collect();
    Statistics {
        depth: vec![],
        pairs,
        coverage,
        pair_masks: masks,
        spans: vec![],
    }
}

#[test]
fn disjoint_dense_components_without_shared_fragments_are_flanks() {
    let contigs = vec![vec![b'A'; 4000], vec![b'C'; 4000]];
    let evidence = stats([vec![1; 100], vec![2; 100]].concat(), vec![3970, 3970]);
    assert!(ranking::unlinked::flanks(&contigs, &evidence, &[0, 1]));
}

#[test]
fn shared_fragments_reject_homologous_alternative_components() {
    let contigs = vec![vec![b'A'; 4000], vec![b'C'; 4000]];
    let evidence = stats(
        [vec![1; 20], vec![2; 20], vec![3; 60]].concat(),
        vec![3970, 3970],
    );
    assert!(!ranking::unlinked::flanks(&contigs, &evidence, &[0, 1]));
}

#[test]
fn a_short_or_single_component_is_never_united() {
    let contigs = vec![vec![b'A'; 4000], vec![b'C'; 400]];
    let evidence = stats([vec![1; 100], vec![2; 100]].concat(), vec![3970, 370]);
    assert!(!ranking::unlinked::flanks(&contigs, &evidence, &[0, 1]));
    assert!(!ranking::unlinked::flanks(&contigs, &evidence, &[0]));
}

#[test]
fn rotation_at_a_join_keeps_native_bases_and_aligned_depth() {
    let sequence = [vec![b'A'; 1200], vec![b'G'; 70], vec![b'C'; 1200]].concat();
    let depth = vec![120u32; sequence.len() - 30];
    let (rotated, observed) = ranking::native(&sequence, &depth, (1200, 1270));
    assert_eq!(rotated.len(), sequence.len() - 70 + 31);
    assert_eq!(observed.len(), rotated.len() - 30);
    assert!(sequence.windows(1200).any(|w| w == &rotated[..1200]));
    assert!(sequence
        .windows(1200)
        .any(|w| w == &rotated[rotated.len() - 1200..]));
}

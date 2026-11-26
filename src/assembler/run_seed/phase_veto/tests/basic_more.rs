use super::{highq, reject_unsupported_recombinants, syn};

#[test]
fn q15_boundary_allows_valid_evidence() {
    let (chim, truth, reads) = syn(true);
    let quals = reads
        .iter()
        .map(|r| vec![b'0'; r.len()])
        .collect::<Vec<_>>(); // Phred+33 Q15
    let (s, _) =
        reject_unsupported_recombinants(vec![chim, truth.clone()], vec![10, 9], &reads, &quals, 0);
    assert_eq!(s, vec![truth]);
}

#[test]
fn protected_micall_seeds_bypass_de_novo_veto() {
    let (chim, truth, reads) = syn(true);
    let quals = highq(&reads);
    let (s, c) = reject_unsupported_recombinants(
        vec![chim.clone(), truth.clone()],
        vec![10, 9],
        &reads,
        &quals,
        1,
    );
    assert_eq!(s, vec![chim, truth]);
    assert_eq!(c, vec![10, 9]);
}

use super::{highq, reject_unsupported_recombinants, syn};

#[test]
fn rejects_linked_recombinant_keeps_truth() {
    let (chim, truth, reads) = syn(true);
    let quals = highq(&reads);
    let (s, c) =
        reject_unsupported_recombinants(vec![chim, truth.clone()], vec![10, 9], &reads, &quals, 0);
    assert_eq!(s, vec![truth]);
    assert_eq!(c, vec![9]);
}

#[test]
fn unlinked_kept_unknown() {
    let (chim, _, reads) = syn(false);
    let quals = highq(&reads);
    let (s, _) = reject_unsupported_recombinants(vec![chim.clone()], vec![1], &reads, &quals, 0);
    assert_eq!(s, vec![chim]);
}

#[test]
fn low_quality_prevents_q15_veto_evidence() {
    let (chim, truth, reads) = syn(true);
    let quals = reads
        .iter()
        .map(|r| vec![b'!'; r.len()])
        .collect::<Vec<_>>();
    let (s, _) = reject_unsupported_recombinants(
        vec![chim.clone(), truth.clone()],
        vec![10, 9],
        &reads,
        &quals,
        0,
    );
    assert_eq!(s, vec![chim, truth]);
}

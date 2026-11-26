use super::{highq, syn, vet_rescue};

#[test]
fn rescue_veto_withholds_chimera_keeps_truth() {
    let (chim, truth, reads) = syn(true);
    let quals = highq(&reads);
    assert!(vet_rescue(chim, &reads, &quals).is_none());
    assert_eq!(vet_rescue(truth.clone(), &reads, &quals), Some(truth));
}

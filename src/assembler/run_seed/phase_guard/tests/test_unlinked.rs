use super::test_support::{synthetic,split};
#[test] fn no_direct_pair_bridge_must_not_infer_recombinant_phase() {
    let (chimera,_,reads)=synthetic(false);
    assert_eq!(split(chimera.clone(),&reads),vec![chimera]);
}
#[test] fn absence_of_pair_data_must_not_veto() {
    let (chimera,_,_)=synthetic(true);
    assert_eq!(split(chimera.clone(),&[]),vec![chimera]);
}

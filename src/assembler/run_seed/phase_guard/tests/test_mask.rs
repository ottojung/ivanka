use super::test_support::synthetic;
use super::{collect::observations,detect::incompatible_link};
#[test] fn ambiguity_mask_preserves_length_and_removes_unsupported_allele_pair() {
    let (chimera,_,reads)=synthetic(true);
    let outputs=super::mask::mask_unsupported_contigs(vec![chimera.clone()],&reads);
    assert_eq!(outputs.len(),1);
    assert_eq!(outputs[0].len(),chimera.len());
    assert_eq!(outputs[0].iter().filter(|&&b|b==b'N').count(),1);
    assert!(incompatible_link(&outputs[0],&reads,
        &observations(&outputs[0],&reads,25)).is_none());
}
#[test] fn ambiguity_mask_does_not_infer_unlinked_phase() {
    let (chimera,_,reads)=synthetic(false);
    let outputs=super::mask::mask_unsupported_contigs(vec![chimera.clone()],&reads);
    assert_eq!(outputs,vec![chimera]);
}

#[test] fn ambiguity_mask_retains_a_directly_supported_haplotype() {
    let (_,truth,reads)=synthetic(true);
    assert_eq!(super::mask::mask_unsupported_contigs(vec![truth.clone()],&reads),
               vec![truth]);
}
#[test] fn ambiguity_mask_abstains_on_same_orientation_mates() {
    let (chimera,_,mut reads)=synthetic(true);
    for pair in reads.chunks_exact_mut(4) {pair.swap(2,3);}
    assert_eq!(super::mask::mask_unsupported_contigs(vec![chimera.clone()],&reads),
               vec![chimera]);
}

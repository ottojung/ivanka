use super::test_support::{synthetic,split};
use super::{collect::observations,detect::incompatible_link};
#[test] fn rejects_unsupported_recombinant_without_discarding_local_sequence() {
    let (chimera,truth,reads)=synthetic(true);
    let contigs=split(chimera.clone(),&reads);
    assert_eq!(contigs.len(),2);
    assert_eq!(contigs.concat(),chimera);
    for fragment in &contigs {
        assert!(incompatible_link(fragment,&reads,&observations(fragment,&reads,25)).is_none());
    }
    assert!(contigs.iter().all(|c|c.len()>=31));
    assert_eq!(contigs[0][200],truth[200]);
    assert_eq!(contigs[1][420-contigs[0].len()],b'T');
}
#[test] fn directly_supported_haplotype_is_retained() {
    let (_,truth,reads)=synthetic(true);
    assert_eq!(split(truth.clone(),&reads),vec![truth]);
}
#[test] fn same_orientation_mates_do_not_create_false_phase_witnesses() {
    let (chimera,_,mut reads)=synthetic(true);
    for pair in reads.chunks_exact_mut(4) {pair.swap(2,3);}
    assert_eq!(split(chimera,&reads).len(),1);
}
#[test] fn maximum_contig_cap_is_not_bypassed() {
    let (chimera,_,reads)=synthetic(true);
    let result=split_unsupported(chimera,&reads);
    assert!(result.is_empty());
}
fn split_unsupported(seq: Vec<u8>,reads:&[Vec<u8>])->Vec<Vec<u8>> {
    super::split::split_unsupported_contigs(vec![seq],reads,1)
}

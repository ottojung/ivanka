#[test] fn ranking_keeps_a_read_backed_local_allele_without_a_reference() {
    for n in [9,10] {
        let (base,variant,reads)=super::test_support::example(n,false);
        let candidates=vec![base.clone(),variant.clone()];
        let old=crate::assembler::ranking::select_supported_contigs(candidates.clone(),vec![100,90],2,0);
        assert_eq!(old,vec![base.clone()]);
        let improved=crate::assembler::ranking::select_supported_contigs_with_reads(candidates,vec![100,90],2,0,&reads);
        if n==9 {assert_eq!(improved,vec![base]);}
        else {assert_eq!(improved,vec![base,variant]);}
    }
}

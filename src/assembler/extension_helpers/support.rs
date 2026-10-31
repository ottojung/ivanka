use std::collections::HashSet;

pub(crate) fn record_extension_support(suffixes:&[Vec<u8>], ids:&[u32],
                            extension:&[u8], support:&mut HashSet<u32>) {
    if extension.is_empty() { return; }
    for (suffix,&id) in suffixes.iter().zip(ids.iter()) {
        if !suffix.is_empty() &&
           suffix.iter().zip(extension).all(|(a,b)|a==b) &&
           suffix[0]==extension[0] {
            support.insert(id);
        }
    }
}

    #[test] fn support_deduplicates_reused_reads_not_multiplicity(){
        let mut support=HashSet::new();
        let x=vec![b"ACGT".to_vec(),b"ACTG".to_vec(),b"ACGT".to_vec()];
        let ids=vec![3,3,4];
        record_extension_support(&x,&ids,b"AC",&mut support);
        assert_eq!(support,HashSet::from([3,4]));
        record_extension_support(&x,&ids,b"ACG",&mut support);
        assert_eq!(support.len(),2);
        let mut none=HashSet::new();
        record_extension_support(&x,&ids,b"TT",&mut none);
        assert!(none.is_empty());
    }

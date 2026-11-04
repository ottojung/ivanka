use super::index::{kmer_codes,unique_flanks,INVALID};
#[test] fn rolling_codes_match_exact_dna_windows() {
    for sample in [b"ACGTACGTNNACGTAGTA".as_slice(),b"AAAACCCCCGGGGTTTT".as_slice()] {
        let result=kmer_codes(sample,4);
        assert_eq!(result.len(),sample.len()-3);
        for (i,w) in sample.windows(4).enumerate() {
            let expected=w.iter().try_fold(0u64,|n,&b|
                Some((n<<2)|match b {b'A'=>0,b'C'=>1,b'G'=>2,b'T'=>3,_=>return None}));
            assert_eq!(result[i],expected.unwrap_or(INVALID));
        }
    }
}
#[test] fn ambiguous_flanks_are_excluded() {
    assert!(unique_flanks(b"ACGTNACGT",2).values().all(Option::is_some));
}

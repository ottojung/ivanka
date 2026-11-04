use super::collect::observations;
use super::test_support::{synthetic,split,reverse_complement};
#[test] fn repeated_identical_pair_sequences_do_not_create_phasing_witnesses() {
    let (chimera,_,reads)=synthetic(true);
    let mut copies=Vec::new();
    for index in [0,1].into_iter().cycle().take(40) {
        copies.extend_from_slice(&reads[index*4..index*4+4]);
    }
    assert_eq!(split(chimera.clone(),&copies),vec![chimera]);
}
#[test] fn overlapping_mates_with_disagreeing_bases_are_not_phased() {
    let (seq,_,_)=synthetic(true);
    let first=seq[150..250].to_vec();
    let mut second=first.clone();
    second[50]=b'C';
    let mut reads=Vec::new();
    reads.push(first.clone());
    reads.push(reverse_complement(&first));
    reads.push(second.clone());
    reads.push(reverse_complement(&second));
    let calls=observations(&seq,&reads,25);
    assert!(calls[0].get(&200).is_none());
}
#[test] fn distant_paired_mappings_are_not_direct_phase_bridges() {
    let (mut chimera,_,reads)=synthetic(true);
    chimera.splice(300..300,vec![b'A';800]);
    // The false apparent pairwise positions now differ by 1020 bases.
    assert_eq!(split(chimera.clone(),&reads),vec![chimera]);
}

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

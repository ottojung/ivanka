use std::collections::HashMap;
use super::dna::{encode, K};
use super::types::{Hit, Reads};
    #[test] fn internal_seed_overhang_can_extend() {
        let seed=b"ACGTACGTACGTACGTACGTACGTACGTACG";
        let mut read=vec![b'G';
        40];
        read.extend_from_slice(seed);
        read.extend_from_slice(b"TTAACCGG");
        let mut index=HashMap::new();
        index.insert(encode(seed).unwrap(),vec![Hit{read:0,pos:40}]);
        let max_read_len=read.len();
        let reads=Reads{seqs:vec![read],index,seed_counts:HashMap::new(),max_read_len,overhang_cache:Default::default(),overlength_rejections:Default::default()};
        let ov=reads.overhangs_with_ids(seed).0;
        assert_eq!(ov,vec![b"TTAACCGG".to_vec()]);
    }


    #[test] fn sliding_query_matches_full_encoder_for_ambiguous_reads() {
        use super::overhang::rolling_query;
        let mut seq=vec![b'A'; 2100];
        let mut rng=0x8bd530f8b2ac51_u64;
        for (i,x) in seq.iter_mut().enumerate() {
            rng^=rng<<13; rng^=rng>>7; rng^=rng<<17;
            *x=if i%127==0 {b'N'} else {b"ACGT"[(rng&3) as usize]};
        }
        let mut previous=None;
        for q in 0..=seq.len()-K {
            let current=rolling_query(&seq,q,previous);
            assert_eq!(current,encode(&seq[q..q+K]),"at {q}");
            previous=current;
        }
    }

    #[test] fn stable_suffix_overhangs_ignore_left_prepend() {
        use super::index::build_index;
        let contig=b"ACGT".repeat(100);
        let mut read=contig[290..].to_vec();
        read.extend_from_slice(b"AG");
        let max_read_len=read.len();
        let index=build_index(&[read.clone()]);
        let reads=Reads{seqs:vec![read],index,seed_counts:HashMap::new(),max_read_len,overhang_cache:Default::default(),overlength_rejections:Default::default()};
        assert!(contig.len()>=reads.max_read_len);
        let original=reads.overhangs_with_ids(&contig);
        let mut prefixed=b"TGCA".repeat(20);
        prefixed.extend_from_slice(&contig);
        let changed=reads.overhangs_with_ids(&prefixed);
        assert!(!original.0.is_empty());
        assert_eq!(original,changed);
    }

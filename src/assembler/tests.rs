use std::collections::{HashMap, HashSet};
use super::reads::{K, encode, decode, rc, Hit, Reads, fasta_seeds};
use super::extension::{CYCLE_MATCH, choose_extension, cycle_end, record_extension_support};
use super::ranking::select_supported_contigs;
use super::seeds::balanced_seed_candidates;

    #[test] fn seed_search_spreads_depth_buckets_deterministically() {
        let mut counts=HashMap::new();
        for i in 0..40u64 {
            counts.insert(i+1000,8000);
            counts.insert(i+2000,90);
            counts.insert(i+3000,32);
        }
        counts.insert(7,14);
        let selected=balanced_seed_candidates(&counts);
        assert_eq!(selected.len(),120);
        let early=selected.iter().take(12).map(|(_,c)|*c).collect::<Vec<_>>();
        for expected in [8000,90,32] {
            assert_eq!(early.iter().filter(|c|**c==expected).count(),4);
        }
        assert!(!selected.iter().any(|(k,_)|*k==7));
        assert_eq!(selected,balanced_seed_candidates(&counts));
    }
    #[test] fn ranking_favors_evidence_density_over_unverified_span() {
        let long=vec![b'A';800];
        let short=vec![b'C';400];
        let output=select_supported_contigs(
            vec![long.clone(),short.clone()],vec![90,80],1,0);
        assert_eq!(output,vec![short]);
    }
    #[test] fn cap_prefers_read_supported_quality_over_length(){
        let input=vec![vec![b'A';900],vec![b'C';180],vec![b'T';31]];
        let output=select_supported_contigs(input,vec![1,9,0],2,0);
        assert_eq!(output.len(),2);
        assert_eq!(output[0].len(),180);
        assert_eq!(output[1].len(),900);
    }
    #[test] fn cap_preserves_short_g2p_seed_and_respects_1000(){
        let seqs=(1..=1200).map(|n|vec![b'A';n]).collect::<Vec<_>>();
        let counts=(1..=1200).map(|n|n).collect::<Vec<_>>();
        let out=select_supported_contigs(seqs,counts,1000,1);
        assert!(out.len()<=1000);
        assert!(out.len()>1);
        assert_eq!(out[0].len(),1);
        assert_eq!(out[1].len(),1200);
        assert!(!out.iter().any(|s|s.len()==31));
    }
    #[test] fn drops_short_nearly_contained_path_but_keeps_novel_locus(){
        let mut rng=0x1234_5678_1234_5678u64;
        let long=(0..900).map(|_|{
            rng^=rng<<13; rng^=rng>>7; rng^=rng<<17;
            b"ACGT"[(rng&3) as usize]
        }).collect::<Vec<u8>>();
        let mut shorter=long[100..700].to_vec();
        shorter[300]=if shorter[300]==b'A' {b'C'} else {b'A'};
        let novel=vec![b'T';400];
        let result=select_supported_contigs(
            vec![long.clone(),shorter,novel.clone()],vec![240,90,60],1000,0);
        assert_eq!(result,vec![long,novel]);
    }
    #[test] fn supported_full_length_path_survives_dense_short_fragments(){
        let mut seqs=(0..40usize).map(|i|{
            let mut seq=vec![b'A';K];
            for j in 0..5 {seq[j*6]=b"ACGT"[(i>>(j*2))&3];}
            seq
        }).collect::<Vec<_>>();
        seqs.push(vec![b'G';900]);
        let mut support=vec![100usize;40];support.push(80);
        let retained=select_supported_contigs(seqs,support,16,0);
        assert!(retained.len()<=16);
        assert!(retained.iter().any(|seq|seq.len()==900));
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
    #[test] fn reverse_complement(){assert_eq!(rc(b"AAGTNC"),b"GNACTT");}
    #[test] fn encode_roundtrip(){let x=b"ACGTACGTACGTACGTACGTACGTACGTACG"; assert_eq!(decode(encode(x).unwrap()),x);}
    #[test] fn read_external_fasta_seeds() {
        let path=std::env::temp_dir().join(format!("ivanka-seeds-{}.fasta",std::process::id()));
        std::fs::write(&path,">seed-one\nacgtACGT\n>seed-two\nGGGG\n>ambiguous\nANNN\n").unwrap();
        let seeds=fasta_seeds(path.to_str().unwrap()).unwrap();
        std::fs::remove_file(&path).unwrap();
        assert_eq!(seeds,vec![b"ACGTACGT".to_vec(),b"GGGG".to_vec()]);
    }
    #[test] fn internal_seed_overhang_can_extend() {
        let seed=b"ACGTACGTACGTACGTACGTACGTACGTACG";
        let mut read=vec![b'G';40];
        read.extend_from_slice(seed);
        read.extend_from_slice(b"TTAACCGG");
        let mut index=HashMap::new();
        index.insert(encode(seed).unwrap(),vec![Hit{read:0,pos:40}]);
        let reads=Reads{seqs:vec![read],index,seed_counts:HashMap::new()};
        let ov=reads.overhangs_with_ids(seed).0;
        assert_eq!(ov,vec![b"TTAACCGG".to_vec()]);
    }
    #[test] fn distant_cycle_is_stopped() {
        let mut rng=0xdeadbeef12345678u64;
        let period=(0..6000).map(|_|{
            rng^=rng<<13; rng^=rng>>7; rng^=rng<<17;
            [b'A',b'C',b'G',b'T'][(rng & 3) as usize]
        }).collect::<Vec<u8>>();
        let mut seq = period.clone();
        seq.extend_from_slice(&period[..CYCLE_MATCH + 100]);
        let cut = cycle_end(&seq).expect("repeated long tract");
        assert_eq!(cut, period.len() + CYCLE_MATCH);
    }
    #[test] fn short_duplicated_tract_is_not_cycle() {
        let mut seq = vec![b'A'; 100];
        seq.extend(std::iter::repeat(b'C').take(4000));
        seq.extend(std::iter::repeat(b'A').take(100));
        assert_eq!(cycle_end(&seq), None);
    }
    #[test] fn extension_consensus(){
        let a=(0..16).map(|_|b"ACGTA".to_vec()).collect::<Vec<_>>();
        assert_eq!(choose_extension(&a,10,4),b"ACGTA");
        let mut b=a; b.extend((0..8).map(|_|b"ATGTA".to_vec()));
        assert_eq!(choose_extension(&b,10,4),b"A");
    }

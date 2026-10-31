use super::input::fasta_seeds;
    #[test] fn read_external_fasta_seeds() {
        let path=std::env::temp_dir().join(format!("ivanka-seeds-{}.fasta",std::process::id()));
        std::fs::write(&path,">seed-one\nacgtACGT\n>seed-two\nGGGG\n>ambiguous\nANNN\n").unwrap();
        let seeds=fasta_seeds(path.to_str().unwrap()).unwrap();
        std::fs::remove_file(&path).unwrap();
        assert_eq!(seeds,vec![b"ACGTACGT".to_vec(),b"GGGG".to_vec()]);
    }

    #[test] fn rolling_seed_counts_match_naive() {
        use super::load::count_sampled_seed_kmers;
        use super::dna::{K,encode,rc};
        use std::collections::HashMap;
        let seq=b"ACGT".repeat(63);
        let mut expected=HashMap::new();
        for i in (0..=seq.len()-K).step_by(3) {
            let f=encode(&seq[i..i+K]).unwrap();
            let r=encode(&rc(&seq[i..i+K])).unwrap();
            *expected.entry(f.min(r)).or_insert(0u32)+=1;
        }
        let mut actual=HashMap::new();
        count_sampled_seed_kmers(&seq,&mut actual);
        assert_eq!(actual,expected);
    }

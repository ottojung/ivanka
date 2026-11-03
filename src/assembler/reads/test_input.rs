use super::input::fasta_seeds;
    #[test] fn read_external_fasta_seeds() {
        let path=std::env::temp_dir().join(format!("ivanka-seeds-{}.fasta",std::process::id()));
        std::fs::write(&path,">seed-one\nacgtACGT\n>seed-two\nGGGG\n>ambiguous\nANNN\n").unwrap();
        let seeds=fasta_seeds(path.to_str().unwrap()).unwrap();
        std::fs::remove_file(&path).unwrap();
        assert_eq!(seeds,vec![b"ACGTACGT".to_vec(),b"GGGG".to_vec()]);
    }

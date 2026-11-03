use super::choose::choose_extension;
    #[test] fn extension_consensus(){
        let a=(0..16).map(|_|b"ACGTA".to_vec()).collect::<Vec<_>>();
        assert_eq!(choose_extension(&a,10,4,100),b"ACGTA");
        let mut b=a;
        b.extend((0..8).map(|_|b"ATGTA".to_vec()));
        assert_eq!(choose_extension(&b,10,4,100),b"A");
    }

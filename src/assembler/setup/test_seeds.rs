use std::collections::HashMap;
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

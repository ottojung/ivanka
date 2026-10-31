use super::{build_index, encode, HashMap, INDEX_STEP, K};

#[test] fn rolling_index_matches_full_windows() {
        for length in [30,31,32,43,44,55,251] {
            let mut seq=vec![b'A';length];let mut rng=0x9a7f_20c3_d6b1_8482_u64;
            for (i,b) in seq.iter_mut().enumerate() {
                rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;
                *b=if i%47==0 {b'N'} else {b"ACGT"[(rng&3) as usize]};
            }
            let mut expected=HashMap::<u64,Vec<(u32,u16)>>::new();if seq.len()>=K {
                for pos in (0..=seq.len()-K).step_by(INDEX_STEP) {
                    if let Some(k)=encode(&seq[pos..pos+K]) {expected.entry(k).or_default().push((0,pos as u16));}
                }
                if (seq.len()-K)%INDEX_STEP!=0 {
                    if let Some(k)=encode(&seq[seq.len()-K..]) {expected.entry(k).or_default().push((0,(seq.len()-K) as u16));}
                }
            }
            let actual=build_index(&[seq]).into_iter().map(|(k,v)| {
                (k,v.into_iter().map(|hit|(hit.read,hit.pos)).collect::<Vec<_>>())
            }).collect::<HashMap<_,_>>();
            assert_eq!(actual,expected,"length={length}");
            for hits in actual.values() {
                let mut unique=std::collections::HashSet::new();
                assert!(hits.iter().all(|hit|unique.insert(*hit)),"duplicate terminal hit, length={length}");
            }
        }
    }

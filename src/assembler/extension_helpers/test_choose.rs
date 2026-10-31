use super::choose::choose_extension;
    #[test] fn extension_consensus(){
        let a=(0..16).map(|_|b"ACGTA".to_vec()).collect::<Vec<_>>();
        assert_eq!(choose_extension(&a,10,4,100),b"ACGTA");
        let mut b=a;
        b.extend((0..8).map(|_|b"ATGTA".to_vec()));
        assert_eq!(choose_extension(&b,10,4,100),b"A");
    }

    #[test] fn direct_overhang_references_match_original_consensus() {
        fn old(overhangs:&[Vec<u8>], min_cov:usize, min_ratio:usize, max_extension:usize)->Vec<u8>{
            let mut out=Vec::new();
            let mut remaining=(0..overhangs.len()).collect::<Vec<_>>();
            for i in 0..max_extension {
                let mut counts=[0usize;4];
                for &x in &remaining {
                    if i<overhangs[x].len() {
                        match overhangs[x][i] {b'A'=>counts[0]+=1,b'C'=>counts[1]+=1,b'G'=>counts[2]+=1,b'T'=>counts[3]+=1,_=>{}}
                    }
                }
                let mut sorted=counts;
                sorted.sort_unstable_by(|a,b|b.cmp(a));
                if sorted[0]<min_cov||sorted[0]<min_ratio.saturating_mul(sorted[1]) {break;}
                let base=match counts.iter().position(|n|*n==sorted[0]).unwrap(){0=>b'A',1=>b'C',2=>b'G',_=>b'T'};
                out.push(base);
                remaining.retain(|x|overhangs[*x].get(i)==Some(&base));
            }
            out
        }
        let mut state=0x741e_521c_6349_3d6au64;
        for n in [0,1,2,6,16,300] {
            let mut overhangs=Vec::new();
            for _ in 0..n {
                let len=(state as usize)%105;
                let mut seq=vec![b'A';len];
                for base in &mut seq {
                    state^=state<<13;state^=state>>7;state^=state<<17;
                    *base=b"ACGTN"[(state%5) as usize];
                }
                overhangs.push(seq);
            }
            for cov in [0,1,2,6,12] {
                for ratio in [0,1,2,4] {
                    let previous=old(&overhangs,cov,ratio,100);
                    assert_eq!(choose_extension(&overhangs,cov,ratio,100),previous,
                        "count={n} cov={cov} ratio={ratio}");
                }
            }
        }
    }

use super::rescue_rank::append_preserving_diversity;

#[test] fn linear_cover_matches_original_across_ambiguous_and_phased_paths() {
    use super::{canonical_kmer,K};
    use std::collections::HashSet;
    fn oracle(v:&mut Vec<Vec<u8>>,rescue:Vec<u8>,cap:usize,protected:usize)->bool {
        if cap==0||rescue.len()<K{return false;}
        if v.len()<cap {v.push(rescue);return true;}
        let cover=|s:&[u8]|->HashSet<u64>{s.windows(K).filter_map(canonical_kmer).collect()};
        let sets=v.iter().map(|s|cover(s)).collect::<Vec<_>>();
        let rs=cover(&rescue);
        let idx=(protected..v.len()).filter(|&i|{
            let mut other=rs.clone();
            for (j,ks) in sets.iter().enumerate(){if i!=j{other.extend(ks.iter().copied());}}
            sets[i].is_subset(&other)
        }).min_by_key(|&i|v[i].len());
        if let Some(i)=idx {v[i]=rescue;true}else{false}
    }
    let mut rng=0x8a3c_0c57_2f6d_4b19u64;
    let mut next=||{rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;rng};
    for case in 0..600 {
        let n=2+(next()%8) as usize;
        let template=(0..150).map(|_|b"ACGTN"[(next()%5) as usize]).collect::<Vec<_>>();
        let mut v=(0..n).map(|i|{
            let len=30+(next()%90) as usize;
            if i%3==0 {template[..len].to_vec()} else {
                (0..len).map(|_|b"ACGTN"[(next()%5) as usize]).collect()
            }
        }).collect::<Vec<_>>();
        let rescue=if case%2==0 {v[(next()%n as u64) as usize].clone()}
            else {(0..(30+(next()%90) as usize)).map(|_|b"ACGTN"[(next()%5) as usize]).collect()};
        let cap=if case%7==0 {n+1}else{n};
        let protected=(next()%(n as u64+1)) as usize;
        let mut expected=v.clone();
        let before=oracle(&mut expected,rescue.clone(),cap,protected);
        let after=append_preserving_diversity(&mut v,rescue,cap,protected);
        assert_eq!((after,v),(before,expected),"case {case}");
    }
}

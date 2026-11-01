use super::cycle::{cycle_end, CYCLE_MATCH};
pub(super) fn encode(seq:&[u8])->Option<u64> {
    if seq.len()!=31 {return None;}
    let mut n=0u64;
    for b in seq {
        let d=match b {b'A'=>0,b'C'=>1,b'G'=>2,b'T'=>3,_=>return None};
        n=(n<<2)|d;
    }
    Some(n)
}
    #[test] fn distant_cycle_is_stopped() {
        let mut rng=0xdeadbeef12345678u64;
        let period=(0..6000).map(|_|{
            rng^=rng<<13;
            rng^=rng>>7;
            rng^=rng<<17;
            [b'A',b'C',b'G',b'T'][(rng & 3) as usize]
        }).collect::<Vec<u8>>();
        let mut seq = period.clone();
        seq.extend_from_slice(&period[..CYCLE_MATCH + 100]);
        let cut = cycle_end(&seq, 31, encode).expect("repeated long tract");
        assert_eq!(cut, period.len() + CYCLE_MATCH);
    }
    #[test] fn short_duplicated_tract_is_not_cycle() {
        let mut seq = vec![b'A';
        100];
        seq.extend(std::iter::repeat(b'C').take(4000));
        seq.extend(std::iter::repeat(b'A').take(100));
        assert_eq!(cycle_end(&seq, 31, encode), None);
    }

#[test] fn cycle_distinct_anchor_count_matches_hashset_oracle() {
    use super::cycle::{repeats,CYCLE_MIN_SPACING};
    use std::collections::HashSet;
    let mut rng=0x8d7e53c1a91f26b4u64;
    for trial in 0..512 {
        let mut tract=vec![b'A';CYCLE_MATCH];
        for (i,b) in tract.iter_mut().enumerate() {
            rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;
            *b=if trial%3==0 && i%17==0 {b'N'} else if trial%7==0 {b'A'}
                else {b"ACGT"[(rng&3) as usize]};
        }
        let mut seq=tract.clone();seq.extend(vec![b'G';CYCLE_MIN_SPACING]);
        let second=seq.len();seq.extend_from_slice(&tract);
        let expected=tract.windows(31).step_by(32).filter_map(encode)
            .collect::<HashSet<_>>().len()>=8;
        assert_eq!(repeats(&seq,0,second,31,encode),expected,"trial {trial}");
    }
}

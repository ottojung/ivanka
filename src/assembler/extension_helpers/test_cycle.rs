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

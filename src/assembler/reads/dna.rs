

pub(crate) const K: usize = 31;
pub(crate) const INDEX_STEP: usize = 12;
pub(crate) const MAX_EXTENSION: usize = 100;
pub(crate) const MAX_CONTIG_LENGTH: usize = 25000;

pub(crate) fn rc(seq: &[u8]) -> Vec<u8> {
    seq.iter().rev().map(|b| match b { b'A' => b'T', b'C' => b'G', b'G' => b'C',
        b'T' => b'A', _ => b'N' }).collect()
}
pub(crate) fn encode(seq: &[u8]) -> Option<u64> {
    if seq.len() != K { return None; }
    let mut n = 0u64;
    for b in seq {
        let d = match b { b'A'=>0, b'C'=>1, b'G'=>2, b'T'=>3, _=>return None };
        n = (n << 2) | d;
    }
    Some(n)
}
pub(crate) fn decode(mut val: u64) -> Vec<u8> {
    let mut out = vec![0;
    K];
    for x in out.iter_mut().rev() {
        *x = match val & 3 { 0=>b'A',1=>b'C',2=>b'G',_=>b'T' };
        val >>= 2;
    }
    out
}

    #[test] fn reverse_complement(){assert_eq!(rc(b"AAGTNC"),b"GNACTT");}
    #[test] fn encode_roundtrip(){let x=b"ACGTACGTACGTACGTACGTACGTACGTACG";
        assert_eq!(decode(encode(x).unwrap()),x);
    }

// Same canonical 31-mers as full-window encoding, one shift per base.
pub(crate) fn rolling_canonical_kmers(seq:&[u8])->impl Iterator<Item=u64>+'_ {
    let (mut forward,mut reverse,mut valid)=(0u64,0u64,0usize);
    seq.iter().filter_map(move |&b| {
        let d=match b {
            b'A'=>0u64,b'C'=>1,b'G'=>2,b'T'=>3,
            _=>{forward=0;reverse=0;valid=0;return None;}
        };
        forward=((forward<<2)&((1u64<<(2*K))-1))|d; reverse=(reverse>>2)|((3-d)<<(2*(K-1)));
        valid+=1; (valid>=K).then_some(forward.min(reverse))
    })
}

#[test] fn rolling_canonical_agrees_with_full_window_encoding() {
    let mut rng=0x123456789abcdef0_u64; let mut seq=vec![b'A';12000];
    for (i,b) in seq.iter_mut().enumerate() {
        rng^=rng<<13; rng^=rng>>7; rng^=rng<<17;
        *b=if i%101==0 {b'N'} else {b"ACGT"[(rng&3) as usize]};
    }
    let expected=seq.windows(K).filter_map(|w|Some(encode(w)?.min(encode(&rc(w))?))).collect::<Vec<_>>();
    assert_eq!(rolling_canonical_kmers(&seq).collect::<Vec<_>>(),expected);
}

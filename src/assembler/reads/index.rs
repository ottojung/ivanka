use std::collections::HashMap;
use super::dna::{K, INDEX_STEP, encode};
use super::types::Hit;

// Move an indexed 31-mer forward by one 12-base sampling step.
fn rolling_index(seq:&[u8],pos:usize,prior:Option<u64>)->Option<u64> {
    let Some(mut code)=prior else {return encode(&seq[pos..pos+K]);};
    for &base in &seq[pos+K-INDEX_STEP..pos+K] {
        let digit=match base {b'A'=>0,b'C'=>1,b'G'=>2,b'T'=>3,_=>return None};
        code=((code<<2)&((1u64<<(2*K))-1))|digit;
    }
    Some(code)
}
pub(super) fn build_index(seqs:&[Vec<u8>])->HashMap<u64,Vec<Hit>> {
        let mut index:HashMap<u64,Vec<Hit>>=HashMap::new();
        for (idx,seq) in seqs.iter().enumerate() {
            if seq.len()<K || seq.len()>u16::MAX as usize {continue;}
            let mut previous=None;
            for pos in (0..=seq.len()-K).step_by(INDEX_STEP) {
                let key=rolling_index(seq,pos,previous);
                previous=key;
                if let Some(kmer)=key{
                    index.entry(kmer).or_default().push(Hit{read:idx as u32,pos:pos as u16});
                }
            }
            // Always index the last k-mer as well.
            if let Some(kmer)=encode(&seq[seq.len()-K..]){
                index.entry(kmer).or_default().push(Hit{read:idx as u32,pos:(seq.len()-K) as u16});
            }
        }
        index
}


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
                if let Some(k)=encode(&seq[seq.len()-K..]) {expected.entry(k).or_default().push((0,(seq.len()-K) as u16));}
            }
            let actual=build_index(&[seq]).into_iter().map(|(k,v)| {
                (k,v.into_iter().map(|hit|(hit.read,hit.pos)).collect::<Vec<_>>())
            }).collect::<HashMap<_,_>>();
            assert_eq!(actual,expected,"length={length}");
        }
    }

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
            // The terminal anchor may already be on the sampled grid.
            let terminal=seq.len()-K;
            if terminal%INDEX_STEP!=0 {
                if let Some(kmer)=encode(&seq[terminal..]) {
                    index.entry(kmer).or_default().push(Hit{read:idx as u32,pos:terminal as u16});
                }
            }
        }
        index
}
#[cfg(test)] mod test;

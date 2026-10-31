#[cfg(test)] mod test_seed;
#[cfg(test)] use super::dna::rc;
use std::collections::HashMap;
use super::dna::{K, INDEX_STEP, encode};
use super::types::Hit;

pub(super) fn build_index(seqs:&[Vec<u8>])->HashMap<u64,Vec<Hit>> {
        let mut index:HashMap<u64,Vec<Hit>>=HashMap::new();
        for (idx,seq) in seqs.iter().enumerate() {
            if seq.len()<K || seq.len()>u16::MAX as usize {continue;}
            for pos in (0..=seq.len()-K).step_by(INDEX_STEP) {
                if let Some(kmer)=encode(&seq[pos..pos+K]){
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
// Exact forward and reverse-complement rolling 31-mer codes.
pub(super) fn add_seed_counts(read:&[u8], counts:&mut HashMap<u64,u32>) {
    let (mut f,mut r,mut valid)=(0u64,0u64,0usize);
    let mask=(1u64<<(2*K))-1;
    for (i,&b) in read.iter().enumerate() {
        let d=match b {
            b'A'=>0,b'C'=>1,b'G'=>2,b'T'=>3,
            _=>{f=0;r=0;valid=0;continue;}
        };
        f=((f<<2)&mask)|d;
        r=(r>>2)|((3-d)<<(2*(K-1)));
        valid+=1;
        if valid>=K && (i+1-K)%3==0 {
            *counts.entry(f.min(r)).or_insert(0)+=1;
        }
    }
}

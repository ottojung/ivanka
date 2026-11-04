use std::collections::HashMap;
use super::index::{kmer_codes,unique_flanks,INVALID};
pub(super) fn observations(seq: &[u8], reads: &[Vec<u8>], a: usize)
    -> Vec<HashMap<usize,u8>> {
    let index=unique_flanks(seq,a);
    let width=2*a+1;
    reads.chunks_exact(4).map(|pair| {
        let mut calls=HashMap::new();
        for read in pair {
            if read.len()<width {continue;}
            let kmers=kmer_codes(read,a);
            for start in 0..=read.len()-width {
                let (left,right)=(kmers[start],kmers[start+a+1]);
                if left==INVALID || right==INVALID {continue;}
                let base=read[start+a];
                if !b"ACGT".contains(&base) {continue;}
                let key=((left as u128)<<(2*a))|right as u128;
                let Some(Some(pos))=index.get(&key) else {continue;};
                calls.entry(*pos).and_modify(|b| {
                    if *b!=base {*b=b'N';}
                }).or_insert(base);
            }
        }
        calls.retain(|_,base|*base!=b'N');
        calls
    }).collect()
}

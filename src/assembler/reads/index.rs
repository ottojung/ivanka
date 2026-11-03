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

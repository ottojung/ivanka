use std::collections::HashSet;
use super::dna::{K, encode};
use super::types::Reads;
impl Reads {
    // Returns overhangs from reads overlapping the right end of contig. No aligner or
    // read mapper: a k-mer is only an inverted-index lookup; the full overlap must be exact.
    pub(crate) fn overhangs_with_ids(&self, contig:&[u8]) -> (Vec<Vec<u8>>,Vec<u32>) {
        if contig.len()<K {return (Vec::new(),Vec::new());}
        let start=contig.len().saturating_sub(250);
        let mut used=HashSet::<u32>::new();
        let mut ext=Vec::new();
        let mut ids=Vec::new();
        for q in start..=contig.len()-K {
            let Some(key)=encode(&contig[q..q+K]) else {continue;};
            let Some(hits)=self.index.get(&key) else {continue;};
            // Pathological repetitive k-mers cannot be used as reliable extension anchors.
            if hits.len()>50000 {continue;}
            for hit in hits {
                let original=hit.read/2;
                if used.contains(&original) {continue;}
                let pos=hit.pos as usize;
                // The contig may be shorter than the aligned read, especially
                // during seeding. In that case the read starts *before* the
                // contig, and the matching anchor is internal to the read.
                let (begin,read_start)=if q>=pos {(q-pos,0)} else {(0,pos-q)};
                let overlap=contig.len()-begin;
                let read=&self.seqs[hit.read as usize];
                if overlap<K || read_start+overlap>=read.len() {continue;}
                if read[read_start..read_start+overlap]!=contig[begin..] {continue;}
                used.insert(original);
                ext.push(read[read_start+overlap..].to_vec());
                ids.push(original);
            }
        }
        (ext,ids)
    }
}

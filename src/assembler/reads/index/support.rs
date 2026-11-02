use std::collections::HashSet;
use super::{Reads,K,encode};

// A sampled index is a locator, never evidence on its own. Verify the
// complete novel 31-mer in each original FASTQ record, counting mates and
// strand orientations separately but not duplicate placements.
fn ten_independent_reads(seq:&[u8],pos:usize,reads:&Reads,budget:&mut usize)->bool {
    let mut ids=HashSet::new();
    for anchor in pos.saturating_sub(11)..=(pos+11).min(seq.len()-K) {
        let Some(key)=encode(&seq[anchor..anchor+K]) else {continue};
        let Some(hits)=reads.index.get(&key) else {continue};
        if hits.len()>50_000 {continue;}
        for hit in hits {
            if *budget==0 {return false;}
            *budget-=1;
            let offset=hit.pos as isize + pos as isize-anchor as isize;
            if offset<0 {continue;}
            let read=&reads.seqs[hit.read as usize];
            if read.get(offset as usize..offset as usize+K)==Some(&seq[pos..pos+K]) {
                ids.insert(hit.read/2);
                if ids.len()>=10 {return true;}
            }
        }
    }
    false
}

// Only rescues a near-duplicate if a previously unrepresented local allele
// is observed in >=10 distinct FASTQ read records. It does NOT establish
// that the entire contig is a read-phased haplotype.
pub(crate) fn read_backed_novel(seq:&[u8],represented:&HashSet<u64>,reads:&Reads,
                                canonical:fn(&[u8])->Option<u64>)->bool {
    let mut tested=HashSet::new();
    let mut budget=20_000usize;
    for (pos,window) in seq.windows(K).enumerate() {
        let Some(key)=canonical(window) else {continue};
        if represented.contains(&key) || !tested.insert(key) {continue;}
        if budget==0 {break;}
        if ten_independent_reads(seq,pos,reads,&mut budget) {return true;}
        // Bounded work; missing evidence conservatively retains the old filter.
        if tested.len()>=256 {break;}
    }
    false
}

use super::reads::{K, encode};
use std::collections::HashSet;
mod filter;
mod score;
mod extra;
#[cfg(test)] mod test_rank;
use score::ranked_candidates;

// A first-pass ranking heuristic, not a calibrated confidence score:
// independent extension-supporting FASTQ records (with multiplicity) times
// assembled span. Preserve G2P-derived seeds before applying the safety cap.
// Orientation-neutral 31-mer identity, used only to avoid reporting
// redundant assembled paths; it never consumes or filters FASTQ reads.
pub(super) fn canonical_kmer(seq:&[u8])->Option<u64> {
    let f=encode(seq)?;
    let mut r=0u64;
    for i in 0..K {r=(r<<2)|(3-((f>>(2*i))&3));}
    Some(f.min(r))
}
pub(super) fn select_supported_contigs(seqs:Vec<Vec<u8>>, counts:Vec<usize>,
                            n:usize, protected:usize)->Vec<Vec<u8>> {
    let candidates=ranked_candidates(seqs,counts,n,protected);
    // Use read support to prioritize assemblies and k-mer novelty to avoid
    // passing hundreds of near-identical contigs into MiCall's stitcher.
    let mut retained=Vec::new();
    let mut represented=HashSet::new();
    let mut duplicates=0usize;
    let mut no_extension_support=0usize;
    let high_redundancy=candidates.len()>n.saturating_mul(2);
    let candref=candidates.clone();
    for (index,(seq,support)) in candidates {
        if retained.len()>=n {break;}
        let seq_copy=seq;
        filter::select(&mut retained,&mut represented,&mut duplicates,
                       &mut no_extension_support,index,seq_copy,support,
                       protected,n,high_redundancy);
    }
    extra::recover(&mut retained,&mut represented,&mut duplicates,&candref,protected,n);
    eprintln!("IVANKA_QUALITY reported={} kmer_redundant={} no_extension_support={}",
              retained.len(),duplicates,no_extension_support);
    retained
}

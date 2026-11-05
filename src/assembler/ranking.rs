use super::ranking_score::{ranked_candidates,supported_snv_alternative,append_only_to_spare_slots};
use std::collections::{HashMap,HashSet};
use super::reads::rolling_canonical_kmers;
use super::reads::{K, encode};

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
    select_supported_contigs_with_kmers(seqs,counts,n,protected,&HashMap::new())
}
pub(super) fn select_supported_contigs_with_kmers(seqs:Vec<Vec<u8>>, counts:Vec<usize>,
                            n:usize, protected:usize, sampled:&HashMap<u64,u32>)->Vec<Vec<u8>> {
    let candidates=ranked_candidates(seqs,counts,n,protected);
    // Use read support to prioritize assemblies and k-mer novelty to avoid
    // passing hundreds of near-identical contigs into MiCall's stitcher.
    let mut retained=Vec::new(); let mut retained_support=Vec::new();let mut variants=Vec::new();
    let mut represented=HashSet::new();
    let mut duplicates=0usize;
    let mut no_extension_support=0usize;
    for (index,(seq,support)) in candidates {
        if retained.len()>=n {break;}
        let is_seed=index<protected;
        if !is_seed && support==0 {
            no_extension_support+=1;
            continue;
        }
        let mut valid=0usize; let mut shared=0usize;
        for k in rolling_canonical_kmers(&seq) {
            valid+=1;
            if represented.contains(&k){shared+=1;}
        }
        // A short sequence nearly contained in a longer supported contig adds
        // little assembly coverage but can divert reads during MiCall remapping.
        // Use a less strict overlap threshold only for these short fragments;
        // equal-length alternatives retain the normal haplotype-diversity rule.
        let longest=retained.iter().map(Vec::len).max().unwrap_or(0);
        let short_shadow=seq.len()*4<=longest*3 && shared*20>=valid*17;
        let snv=supported_snv_alternative(&seq,support,&retained,&retained_support,
                                            sampled,canonical_kmer);
        if !is_seed && valid>0 && (shared*20>=valid*19 || short_shadow) {
            if snv {variants.push(seq);} else {duplicates+=1;}
            continue;
        }
        for k in rolling_canonical_kmers(&seq) {represented.insert(k);}
        retained.push(seq);
        retained_support.push(support);
    }
    let appended=append_only_to_spare_slots(&mut retained,variants,n,&mut represented,canonical_kmer);
    eprintln!("IVANKA_QUALITY reported={} kmer_redundant={} no_extension_support={} snv_spare_slots={}",
              retained.len(),duplicates,no_extension_support,appended);
    retained
}

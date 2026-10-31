use std::collections::HashSet;
use super::dna::{K, encode};

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
    assert_eq!(seqs.len(),counts.len());
    let mut candidates=seqs.into_iter().zip(counts).enumerate().collect::<Vec<_>>();
    let mut spans=candidates.iter().filter(|(i,(_,reads))|*i>=protected && *reads>0)
        .map(|(i,(seq,reads))|(*i,(*reads as u128)*(seq.len() as u128)))
        .collect::<Vec<_>>();
    spans.sort_unstable_by(|a,b|b.1.cmp(&a.1).then_with(||a.0.cmp(&b.0)));
    let span_favorites=spans.into_iter().take(if candidates.len()>n.saturating_mul(2) {(n/2).min(8)} else {0})
        .map(|(i,_)|i).collect::<HashSet<_>>();
    candidates.sort_unstable_by(|a,b|{
        let a_span=span_favorites.contains(&a.0);
        let b_span=span_favorites.contains(&b.0);
        let a_protected=a.0<protected;
        let b_protected=b.0<protected;
        // Approximate read support per assembled base, to avoid rewarding
        // overextended paths purely for being long. Compare ratios using
        // multiplication rather than truncating integer division.
        let a_score=(a.1.1 as u128)*(b.1.0.len() as u128);
        let b_score=(b.1.1 as u128)*(a.1.0.len() as u128);
        b_protected.cmp(&a_protected)
            .then_with(||b_span.cmp(&a_span))
            .then_with(||b_score.cmp(&a_score))
            .then_with(||b.1.1.cmp(&a.1.1))
            .then_with(||b.1.0.len().cmp(&a.1.0.len()))
            .then_with(||a.1.0.cmp(&b.1.0))
    });
    // Use read support to prioritize assemblies and k-mer novelty to avoid
    // passing hundreds of near-identical contigs into MiCall's stitcher.
    let mut retained=Vec::new();
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
        let mut valid=0usize;
        let mut shared=0usize;
        for window in seq.windows(K) {
            if let Some(k)=canonical_kmer(window) {
                valid+=1;
                if represented.contains(&k){shared+=1;}
            }
        }
        // A short sequence nearly contained in a longer supported contig adds
        // little assembly coverage but can divert reads during MiCall remapping.
        // Use a less strict overlap threshold only for these short fragments;
        // equal-length alternatives retain the normal haplotype-diversity rule.
        let longest=retained.iter().map(Vec::len).max().unwrap_or(0);
        let short_shadow=seq.len()*4<=longest*3 && shared*20>=valid*17;
        if !is_seed && valid>0 && (shared*20>=valid*19 || short_shadow) {
            duplicates+=1;
            continue;
        }
        for window in seq.windows(K) {
            if let Some(k)=canonical_kmer(window) {represented.insert(k);}
        }
        retained.push(seq);
    }
    eprintln!("IVANKA_QUALITY reported={} kmer_redundant={} no_extension_support={}",
              retained.len(),duplicates,no_extension_support);
    retained
}

use super::ranking::canonical_kmer;
use super::reads::K;
use super::reads::{Reads, decode};
use super::setup::balanced_seed_candidates;
use super::extension::extend;
use std::collections::HashSet;

pub(super) fn assemble_candidates(candidates:Vec<(u64,u32)>, reads:&Reads, contigs:&mut Vec<Vec<u8>>, supporting_counts:&mut Vec<usize>) {
    let mut attempted=0usize;let mut attempted_seeds=HashSet::new();
    for (seed,count) in candidates {
        if attempted>=1000 || count<15 {break;}
        let seedseq=decode(seed);
        // A k-mer can occur in both a dominant strain and a distinct supported
        // haplotype. Keep independent seed starts rather than treating a
        // previously traversed 31-mer as proof of redundant full contigs.
        // The bounded attempt budget and final read-support/novelty ranking
        // still cap work and reported output.
        attempted+=1;attempted_seeds.insert(seed);
        let (seq,support)=extend(seedseq,&reads,4,1);
        if !seq.is_empty() {
            eprintln!("candidate {} coverage {} produced {} nt",attempted,count,seq.len());
            // Do not merge contigs, merely suppress exact contained duplicates.
            if !contigs.iter().any(|c|c.windows(seq.len()).any(|w|w==seq)) {
                contigs.push(seq);
                supporting_counts.push(support);
            }
        }
        if attempted%20==0 {eprintln!("tried {} seeds, accepted {}",attempted,contigs.len());}
    }
    // A second bounded, high-evidence search complements balanced-depth
    // exploration. We deliberately revisit seeds represented in an earlier
    // contig: a different internal anchor can extend through a difficult
    // junction, while final support/novelty selection still de-duplicates.
    let mut deep=reads.seed_counts.iter()
        .filter(|(_,count)|**count>=15)
        .map(|(&seed,&count)|(seed,count)).collect::<Vec<_>>();
    deep.sort_unstable_by(|a,b|b.1.cmp(&a.1).then_with(||a.0.cmp(&b.0)));
    let mut rescued=0usize;
    for (seed,count) in deep.into_iter().take(400) {
        // Re-running deterministic extension on an identical anchor adds no contig.
        if attempted_seeds.contains(&seed) {continue;}
        let (seq,support)=extend(decode(seed),&reads,4,1);
        if seq.is_empty() {continue;}
        if !contigs.iter().any(|c|c.windows(seq.len()).any(|w|w==seq)) {
            contigs.push(seq);
            supporting_counts.push(support);
            rescued+=1;
        }
        if rescued%20==0 && rescued>0 {
            eprintln!("high-depth rescue considered seed support {}",count);
        }
    }
    eprintln!("Ivanka supplementary high-depth seeds produced {} novel contigs",rescued);
}
mod rescue;
mod rescue_rank;
pub(super) use rescue::rescue_short;

pub(super) use rescue_rank::append_preserving_diversity;

#[cfg(test)] mod rescue_rank_test;

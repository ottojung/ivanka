use std::fs::File;
use std::io::{self, BufWriter, Write};
use std::path::Path;
use std::time::Instant;
use super::dna::{K, decode};
use super::input::fasta_seeds;
use super::reads::Reads;
use super::extension::extend;
use super::ranking::select_supported_contigs;
use super::cli::parse;
use super::seeds::balanced_seed_candidates;

pub(crate) fn run()->Result<(),Box<dyn std::error::Error>> {
    let (a,b,out,max,max_pairs,seeds_path)=parse().map_err(io::Error::other)?;
    let now=Instant::now();
    let reads=Reads::load(&a,&b,max_pairs)?;
    let candidates=balanced_seed_candidates(&reads.seed_counts);
    let mut contigs=Vec::<Vec<u8>>::new();
    let mut supporting_counts=Vec::<usize>::new();
    if let Some(ref seeds_file) = seeds_path {
        let supplied=fasta_seeds(seeds_file)?;
        eprintln!("received {} MiCall G2P seed contigs", supplied.len());
        let seed_quota=(max / 3).max(1);
        for seed in supplied.into_iter().filter(|seq|seq.len()>=K).take(seed_quota) {
            let supplied_len=seed.len(); let (extended,support)=extend(seed,&reads,6,2);
            if extended.len()>=supplied_len &&
               !contigs.iter().any(|c|c.windows(extended.len()).any(|w|w==extended)) {
                contigs.push(extended);
                supporting_counts.push(support);
            }
        }
    }
    let protected_seed_count=contigs.len();
    let mut attempted=0usize;
    for (seed,count) in candidates {
        if attempted>=1000 {break;}
        if count<15 {break;}
        let seedseq=decode(seed);
        // A k-mer can occur in both a dominant strain and a distinct supported
        // haplotype. Keep independent seed starts rather than treating a
        // previously traversed 31-mer as proof of redundant full contigs.
        // The bounded attempt budget and final read-support/novelty ranking
        // still cap work and reported output.
        attempted+=1;
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
    eprintln!("Ivanka ranking {} candidates by distinct contributing FASTQ records × contig length; {} MiCall seeds protected",contigs.len(),protected_seed_count);
    let contigs=select_supported_contigs(contigs,supporting_counts,max,protected_seed_count);
    let mut w=BufWriter::new(File::create(Path::new(&out))?);
    for (i,c) in contigs.iter().enumerate(){
        writeln!(w,">ivanka_{} len={}",i+1,c.len())?;
        for line in c.chunks(80){w.write_all(line)?;w.write_all(b"\n")?;}
    }
    w.flush()?;
    eprintln!("Ivanka wrote {} contigs in {:.1}s",contigs.len(),now.elapsed().as_secs_f64());
    Ok(())
}

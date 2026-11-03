use std::fs::File;
use std::io::{self, BufWriter, Write};
use std::path::Path;
use std::time::Instant;
use super::reads::{K, fasta_seeds, Reads};
use super::extension::extend;
use super::ranking::select_supported_contigs;
use super::setup::{parse, balanced_seed_candidates};
use super::run_seed::assemble_candidates;

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
            let supplied_len=seed.len();
            let (extended,support)=extend(seed,&reads,6,2);
            if extended.len()>=supplied_len &&
               !contigs.iter().any(|c|c.windows(extended.len()).any(|w|w==extended)) {
                contigs.push(extended);
                supporting_counts.push(support);
            }
        }
    }
    let protected_seed_count=contigs.len();
    assemble_candidates(candidates,&reads,&mut contigs,&mut supporting_counts);
    eprintln!("Ivanka ranking {} candidates by distinct contributing FASTQ records × contig length; {} MiCall seeds protected",contigs.len(),protected_seed_count);
    let contigs=select_supported_contigs(contigs,supporting_counts,max,protected_seed_count);
    let mut w=BufWriter::new(File::create(Path::new(&out))?);
    for (i,c) in contigs.iter().enumerate(){
        writeln!(w,">ivanka_{} len={}",i+1,c.len())?;
        for line in c.chunks(80){w.write_all(line)?;
            w.write_all(b"\n")?
            ;}
    }
    w.flush()?;
    eprintln!("Ivanka wrote {} contigs in {:.1}s",contigs.len(),now.elapsed().as_secs_f64());
    Ok(())
}

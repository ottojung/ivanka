mod finish;
mod seeds;
use super::extension::extend;
use super::ranking::{
    canonical_kmer, select_supported_contigs, select_supported_contigs_with_kmers,
};
use super::reads::{fasta_seeds, Reads, K};
use super::run_seed::{append_preserving_diversity, assemble_candidates, rescue_short};
use super::setup::{balanced_seed_candidates, parse, write_fasta, write_snv_audit};
use std::io;
use std::time::Instant;

pub(crate) fn run() -> Result<(), Box<dyn std::error::Error>> {
    let (a, b, out, max, max_pairs, seeds_path, audit_path) = parse().map_err(io::Error::other)?;
    let now = Instant::now();
    let reads = Reads::load(&a, &b, max_pairs)?;
    let candidates = balanced_seed_candidates(&reads.seed_counts);
    let mut contigs = Vec::<Vec<u8>>::new();
    let mut supporting_counts = Vec::<usize>::new();
    seeds::attach(
        seeds_path.as_deref(),
        &reads,
        max,
        &mut contigs,
        &mut supporting_counts,
    )?;
    let protected_seed_count = contigs.len();
    assemble_candidates(candidates, &reads, &mut contigs, &mut supporting_counts);
    let rescue = rescue_short(&a, &b, &reads, max_pairs, &contigs)?;
    eprintln!("Ivanka ranking {} candidates by FASTQ support × contig length; {} supplied seeds protected",contigs.len(),protected_seed_count);
    let written = finish::write(
        &out,
        max,
        protected_seed_count,
        &reads,
        audit_path.as_deref(),
        contigs,
        supporting_counts,
        rescue,
    )?;
    eprintln!(
        "Ivanka wrote {} contigs in {:.1}s",
        written,
        now.elapsed().as_secs_f64()
    );
    Ok(())
}

mod finish;
mod prepare;
mod read_backed;
mod seeds;
mod write_results;
use super::extension::extend;
use super::ranking::{
    canonical_kmer, select_supported_contigs, select_supported_contigs_with_kmers,
};
use super::reads::{encode, fasta_seeds, Reads, K};
use super::run_seed::{append_preserving_diversity, assemble_candidates, rescue_short};
use super::setup::{balanced_seed_candidates, parse, write_fasta, write_snv_audit, Config};
use std::io;
use std::time::Instant;

pub(crate) fn run() -> Result<(), Box<dyn std::error::Error>> {
    let config = parse().map_err(io::Error::other)?;
    let now = Instant::now();
    let prepared = prepare::assemble(&config)?;
    let standard = config.max_pairs.is_none()
        && config.max_contigs == 16
        && config.seeds.is_none()
        && config.audit.is_none();
    let written = finish::write(
        &config.output,
        config.max_contigs,
        config.audit.as_deref(),
        standard,
        prepared,
    )?;
    eprintln!(
        "Ivanka wrote {} contigs in {:.1}s",
        written,
        now.elapsed().as_secs_f64()
    );
    Ok(())
}

use super::{assemble_candidates, balanced_seed_candidates, rescue_short, seeds, Config, Reads};
use std::error::Error;

/// The selected candidates still carry their original per-read extension
/// support; the protected prefix is kept separate from discovered contigs.
pub(super) struct Prepared {
    pub(super) reads: Reads,
    pub(super) contigs: Vec<Vec<u8>>,
    pub(super) support: Vec<usize>,
    pub(super) protected: usize,
    pub(super) rescue: Option<Vec<u8>>,
}

pub(super) fn assemble(config: &Config) -> Result<Prepared, Box<dyn Error>> {
    let reads = Reads::load(&config.reads1, &config.reads2, config.max_pairs)?;
    let candidates = balanced_seed_candidates(&reads.seed_counts);
    let mut contigs = Vec::<Vec<u8>>::new();
    let mut supporting_counts = Vec::<usize>::new();
    seeds::attach(
        config.seeds.as_deref(),
        &reads,
        config.max_contigs,
        &mut contigs,
        &mut supporting_counts,
    )?;
    let protected_seed_count = contigs.len();
    assemble_candidates(candidates, &reads, &mut contigs, &mut supporting_counts)?;
    let rescue = rescue_short(
        &config.reads1,
        &config.reads2,
        &reads,
        config.max_pairs,
        &contigs,
    )?;
    eprintln!(
        concat!(
            "Ivanka ranking {} candidates by read-support density ",
            "with span-favourite priority; {} supplied seeds protected"
        ),
        contigs.len(),
        protected_seed_count,
    );
    Ok(Prepared {
        reads,
        contigs,
        support: supporting_counts,
        protected: protected_seed_count,
        rescue,
    })
}

use super::{decode, extend, HashSet, Reads};
mod deep;
mod experiment_budget;
mod primary;
pub(crate) fn assemble_candidates(
    candidates: Vec<(u64, u32)>,
    reads: &Reads,
    contigs: &mut Vec<Vec<u8>>,
    supporting_counts: &mut Vec<usize>,
) -> Result<(), String> {
    let (primary_limit, rescue_limit) = experiment_budget::limits()?;
    let attempted_seeds =
        primary::assemble_primary(candidates, reads, contigs, supporting_counts, primary_limit);
    deep::assemble_deep(
        reads,
        contigs,
        supporting_counts,
        rescue_limit,
        &attempted_seeds,
    );
    Ok(())
}

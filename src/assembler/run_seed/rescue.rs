mod selection;
use super::{assemble_candidates, balanced_seed_candidates, Reads};
use selection::best_long;
// A high-depth assembly with no long contig may have followed noisy joins.
// Supplement, never replace, the full-read candidates with a bounded prefix.
fn eligible(limit: Option<usize>, oriented: usize, longest: usize, rejects: usize) -> bool {
    limit.is_none() && oriented > 40000 && longest < 1000 && rejects > 0
}
// Only one independently supported long rescue enters final ranking. The
// full-read minority candidates must not be displaced by a second large pool.

pub(crate) fn rescue_short(
    a: &str,
    b: &str,
    reads: &Reads,
    limit: Option<usize>,
    contigs: &[Vec<u8>],
) -> std::io::Result<Option<Vec<u8>>> {
    if !eligible(
        limit,
        reads.seqs.len(),
        contigs.iter().map(Vec::len).max().unwrap_or(0),
        reads.overlength_rejections.get(),
    ) {
        return Ok(None);
    }
    let subset = Reads::load(a, b, Some(10000))?;
    let (mut more, mut supports) = (Vec::new(), Vec::new());
    assemble_candidates(
        balanced_seed_candidates(&subset.seed_counts),
        &subset,
        &mut more,
        &mut supports,
    )
    .map_err(std::io::Error::other)?;
    let rescued = best_long(more, supports, contigs).map(|(seq, _)| seq);
    eprintln!(
        "Ivanka high-depth long-contig rescue found {} supported paths",
        usize::from(rescued.is_some())
    );
    Ok(rescued)
}

#[cfg(test)]
mod tests;

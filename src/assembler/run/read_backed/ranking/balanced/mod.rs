mod evidence;
#[cfg(test)]
mod tests;
use super::{Statistics, K};
use evidence::scan;

// A co-abundant, near-identical second component carries private 31-mer
// islands the dominant component lacks. Reads must support those islands at
// a depth comparable to the dominant component: a co-abundant second
// haplotype keeps near-full depth across shared-plus-private read pairs,
// while a minor component drops to its abundance fraction. Deeper evidence
// signals a superposition, not one defensible phase. Bounded private size
// and two separated islands exclude whole-genome duplicates and isolated
// substitutions. Truth never enters this decision.
const MIN_PRIVATE_PCT: usize = 10;
const MAX_PRIVATE_PCT: usize = 60;
const MIN_RUN: usize = 150;
const MIN_RUNS: usize = 2;
const MIN_DEPTH_PCT: u32 = 80;
const MAX_DEPTH_PCT: u32 = 105;

pub(super) fn qualifies(
    contigs: &[Vec<u8>],
    stats: &Statistics,
    selected: u16,
    primary: usize,
    candidate: usize,
) -> bool {
    let positions = contigs[candidate].len().saturating_sub(K - 1);
    if positions == 0 || stats.pairs[candidate] * 10 < stats.pairs[primary] * 9 {
        return false;
    }
    let (Some(dominant), Some(candidate_depth)) =
        (stats.depth.get(primary), stats.depth.get(candidate))
    else {
        return false;
    };
    if dominant.is_empty() || candidate_depth.len() < positions {
        return false;
    }
    let mut dominant = dominant.clone();
    dominant.sort_unstable();
    let baseline = dominant[dominant.len() / 2].max(1);
    let (count, longest, islands, median_depth) =
        scan(contigs, stats, selected, candidate, MIN_RUN);
    if count * 100 < positions * MIN_PRIVATE_PCT
        || count * 100 > positions * MAX_PRIVATE_PCT
        || islands < MIN_RUNS
        || longest >= positions
    {
        return false;
    }
    median_depth * 100 >= baseline * MIN_DEPTH_PCT && median_depth * 100 <= baseline * MAX_DEPTH_PCT
}

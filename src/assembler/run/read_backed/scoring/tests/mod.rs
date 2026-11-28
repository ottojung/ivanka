mod diversity;
mod duplicates;
mod loci;
mod scan_equivalence;
mod support;

pub(super) fn sig_count(stats: &super::Statistics, i: usize) -> usize {
    stats.exclusive_ranges[i]
        .iter()
        .map(|&(p, _, _)| stats.pair_signatures[p as usize])
        .collect::<std::collections::HashSet<_>>()
        .len()
}

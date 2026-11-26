use super::dedup;
use super::detect;
use super::Evidence;

// Two workers bound concurrent per-candidate scratch allocations (each scan
// owns its call lists and band arrays); the evidence itself is shared by
// immutable reference and never duplicated across workers.
const MAX_WORKERS: usize = 2;

// The veto verdict is a pure function of (candidate, original read pairs).
// Results are written back in input order, so selection and guard logging are
// unaffected by worker scheduling.
pub(super) fn evaluate(
    ev: &Evidence,
    seqs: &[Vec<u8>],
    reads: &[Vec<u8>],
    protected: usize,
) -> Vec<bool> {
    let (mut verdict, first, fresh) = dedup::plan(seqs, protected);
    let mut results = vec![false; fresh.len()];
    let threads = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(1)
        .min(MAX_WORKERS);
    let chunk = fresh.len().div_ceil(threads).max(1);
    std::thread::scope(|scope| {
        for (idxs, out) in fresh.chunks(chunk).zip(results.chunks_mut(chunk)) {
            scope.spawn(move || {
                for (k, &i) in idxs.iter().enumerate() {
                    out[k] = detect::incompatible(&seqs[i], reads, &ev.preps, &ev.sigs);
                }
            });
        }
    });
    dedup::propagate(&mut verdict, &first, &fresh, &results);
    verdict
}

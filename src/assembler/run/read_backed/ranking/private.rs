use super::{
    retained::{self, Keys},
    K,
};

const MIN_DEPTH: u32 = 3;
const MIN_RUN: usize = 8;

// Private windows the original read pairs actually cover, and their longest
// contiguous run. Whole-contig breadth cannot prove a private tail is derived
// from reads, so per-window read-pair depth gates both the count and the run.
pub(super) fn scores(
    contigs: &[Vec<u8>],
    depth: &[Vec<u32>],
    retained: &Keys,
) -> Vec<(usize, usize, usize)> {
    (0..contigs.len())
        .map(|i| {
            let reading = depth.get(i).map(Vec::as_slice).unwrap_or_default();
            evidence(&contigs[i], reading, retained)
        })
        .collect()
}

pub(super) fn qualifies(evidence: (usize, usize, usize), positions: usize, strong: bool) -> bool {
    let (_, supported, run) = evidence;
    strong || (supported * 10 >= positions && supported * 2 <= positions && run > 0)
}

fn evidence(contig: &[u8], depth: &[u32], retained: &Keys) -> (usize, usize, usize) {
    let (mut private, mut supported, mut run, mut longest) = (0, 0, 0, 0);
    for (i, window) in contig.windows(K).enumerate() {
        let Ok(key) = <[u8; K]>::try_from(window) else {
            longest = close(run, longest);
            run = 0;
            continue;
        };
        if retained.contains(&key) || retained.contains(&retained::reverse(window)) {
            longest = close(run, longest);
            run = 0;
            continue;
        }
        private += 1;
        if depth.get(i).copied().unwrap_or(0) < MIN_DEPTH {
            longest = close(run, longest);
            run = 0;
            continue;
        }
        supported += 1;
        run += 1;
    }
    (private, supported, close(run, longest))
}

fn close(run: usize, longest: usize) -> usize {
    longest.max(if run >= MIN_RUN { run } else { 0 })
}

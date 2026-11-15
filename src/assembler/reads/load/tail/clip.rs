use super::{count_sampled_seed_kmers, infer, rc, HashMap, K};

/// Clip only observed copies; rebuild seed depth from identical clipped reads.
pub(crate) fn trim(seqs: &mut [Vec<u8>], seeds: &mut HashMap<u64, u32>) -> usize {
    let Some(suffix) = infer::common(seqs) else {
        return 0;
    };
    let mut clipped = 0usize;
    for pair in seqs.chunks_exact_mut(4) {
        for original in [0, 2] {
            if pair[original].len() < K + suffix.len() || !pair[original].ends_with(&suffix) {
                continue;
            }
            let new_length = pair[original].len() - suffix.len();
            pair[original].truncate(new_length);
            pair[original + 1] = rc(&pair[original]);
            clipped += 1;
        }
    }
    if clipped > 0 {
        seeds.clear();
        for pair in seqs.chunks_exact(4).take(50_000) {
            count_sampled_seed_kmers(&pair[0], seeds);
            count_sampled_seed_kmers(&pair[2], seeds);
        }
        eprintln!(
            "IVANKA_ADAPTIVE_TERMINAL_TAIL length={} clipped_mates={}",
            suffix.len(),
            clipped
        );
    }
    clipped
}

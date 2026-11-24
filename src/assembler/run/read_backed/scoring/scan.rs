use super::accumulate::Accumulator;
use super::{index::Hits, Reads, K};

/// Scan original read pairs, accumulating depth, pair counts and per-pair masks.
pub(super) fn scan(
    contigs: &[Vec<u8>],
    reads: &Reads,
    hits: &Hits,
) -> (Vec<Vec<u32>>, Vec<usize>, Vec<u16>) {
    let mut depth: Vec<Vec<u32>> = contigs
        .iter()
        .map(|seq| vec![0; seq.len().saturating_sub(K - 1)])
        .collect();
    let lengths: Vec<usize> = depth.iter().map(Vec::len).collect();
    let mut pairs = vec![0usize; contigs.len()];
    let mut pair_masks = Vec::with_capacity(80_000);
    let mut accum = Accumulator::new(&lengths);
    for oriented in reads.seqs.chunks_exact(4).take(80_000) {
        accum.begin();
        for read in [&oriented[0], &oriented[2]] {
            if read.len() < K {
                continue;
            }
            for pos in (0..=read.len() - K).step_by(2) {
                if let Some(locations) = hits.get(&read[pos..pos + K]) {
                    for &(candidate, locus) in locations {
                        accum.insert(candidate, locus);
                    }
                }
            }
        }
        let mut mask = 0u16;
        accum.apply(|candidate, loci| {
            if loci.len() >= 2 {
                mask |= 1 << candidate;
                pairs[candidate] += 1;
                for &locus in loci {
                    depth[candidate][locus] += 1;
                }
            }
        });
        pair_masks.push(mask);
    }
    (depth, pairs, pair_masks)
}

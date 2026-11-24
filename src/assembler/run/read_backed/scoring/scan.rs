use super::accumulate::Accumulator;
use super::index::{self, Hits};
use super::spans;
use super::{Reads, K};

pub(super) type Scan = (
    Vec<Vec<u32>>,
    Vec<usize>,
    Vec<u16>,
    Vec<Vec<(usize, usize)>>,
);

/// Byte-equivalent accumulator with per-pair span capture. Sampled start
/// positions and the both-orientation scan are unchanged; only the probe
/// identity is a rolling canonical packed key instead of 31 bytes.
pub(super) fn scan(contigs: &[Vec<u8>], reads: &Reads, hits: &Hits) -> Scan {
    let mut depth: Vec<Vec<u32>> = contigs
        .iter()
        .map(|seq| vec![0; seq.len().saturating_sub(K - 1)])
        .collect();
    let lengths: Vec<usize> = depth.iter().map(Vec::len).collect();
    let mut pairs = vec![0usize; contigs.len()];
    let mut pair_masks = Vec::with_capacity(80_000);
    let mut spans = vec![Vec::new(); contigs.len()];
    let mut accum = Accumulator::new(&lengths);
    for oriented in reads.seqs.chunks_exact(4).take(80_000) {
        accum.begin();
        for read in [&oriented[0], &oriented[2]] {
            for (start, key) in index::rolling(read) {
                if start & 1 != 0 {
                    continue;
                }
                if let Some(locations) = hits.get(&key) {
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
                spans[candidate].push(spans::extremes(loci));
                for &locus in loci {
                    depth[candidate][locus] += 1;
                }
            }
        });
        pair_masks.push(mask);
    }
    (depth, pairs, pair_masks, spans)
}

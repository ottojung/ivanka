use super::{evidence, scan, spans, Hits, Reads, Statistics, K};

/// Count each original read pair once per contig, irrespective of hit count.
pub(super) fn count(contigs: &[Vec<u8>], reads: &Reads, hits: &Hits) -> Statistics {
    let mut depth = contigs
        .iter()
        .map(|seq| vec![0; seq.len().saturating_sub(K - 1)])
        .collect::<Vec<_>>();
    let (mut pairs, mut spans) = (vec![0usize; contigs.len()], vec![Vec::new(); contigs.len()]);
    let (mut pair_masks, mut exclusive_masks, mut pair_signatures) =
        (Vec::new(), Vec::new(), Vec::new());
    let mut exclusive_ranges = vec![Vec::new(); contigs.len()];
    for oriented in reads.seqs.chunks_exact(4).take(80_000) {
        let (matched, exclusive) = scan::pair_loci(hits, &oriented[0], &oriented[2]);
        let pair = pair_masks.len();
        pair_signatures.push(evidence::signature(&oriented[0], &oriented[2]));
        let mut mask = 0u16;
        for (candidate, loci) in matched {
            if loci.len() < 2 {
                continue;
            }
            mask |= 1 << candidate;
            pairs[candidate] += 1;
            spans[candidate].push(spans::extremes(&loci));
            for locus in loci {
                depth[candidate][locus] += 1;
            }
        }
        let mut exclusive_mask = 0u16;
        for (candidate, loci) in exclusive {
            if loci.len() >= 2 {
                exclusive_mask |= 1 << candidate;
                evidence::note_exclusive(&mut exclusive_ranges, candidate, pair, &loci);
            }
        }
        pair_masks.push(mask);
        exclusive_masks.push(exclusive_mask);
    }
    Statistics {
        coverage: spans::coverage(&depth),
        depth,
        pairs,
        pair_masks,
        exclusive_masks,
        pair_signatures,
        exclusive_ranges,
        spans,
    }
}

use super::{anchors, anchors::Mate, Hits, Reads, K};
use std::collections::HashSet;

pub(crate) struct Statistics {
    pub(crate) depth: Vec<Vec<u32>>,
    pub(crate) pairs: Vec<usize>,
    pub(crate) coverage: Vec<usize>,
    pub(crate) concordant: Vec<usize>,
}

/// Count each original read pair once per contig, irrespective of hit count.
/// Concordance is a separate tie-breaker and never changes depth or pair counts.
pub(crate) fn count(contigs: &[Vec<u8>], reads: &Reads, hits: &Hits) -> Statistics {
    let mut depth = contigs
        .iter()
        .map(|seq| vec![0; seq.len().saturating_sub(K - 1)])
        .collect::<Vec<_>>();
    let mut pairs = vec![0usize; contigs.len()];
    let mut concordant = vec![0usize; contigs.len()];
    for oriented in reads.seqs.chunks_exact(4).take(80_000) {
        let mut mates = [Mate::new(), Mate::new()];
        anchors::anchors(hits, &oriented[0], &mut mates[0]);
        anchors::anchors(hits, &oriented[2], &mut mates[1]);
        let candidates = mates[0]
            .keys()
            .chain(mates[1].keys())
            .copied()
            .collect::<HashSet<_>>();
        for candidate in candidates {
            let loci = anchors::loci(&mates[0], &mates[1], candidate);
            if loci.len() < 2 {
                continue;
            }
            pairs[candidate] += 1;
            for locus in loci {
                depth[candidate][locus] += 1;
            }
            if anchors::linked(&mates[0], &mates[1], candidate) {
                concordant[candidate] += 1;
            }
        }
    }
    let coverage = depth
        .iter()
        .map(|d| d.iter().filter(|&&v| v >= 3).count())
        .collect();
    Statistics {
        depth,
        pairs,
        coverage,
        concordant,
    }
}

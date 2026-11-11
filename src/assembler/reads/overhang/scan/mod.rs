mod match_hit;
mod rolling;
use super::Reads;
use super::{encode, K};
pub(crate) use rolling::rolling_query;
// Scan successive query 31-mers by shifting their two-bit codes rather than
// re-encoding 31 bases on every overlapping index lookup.
impl Reads {
    // Returns overhangs from reads overlapping the right end of contig. No aligner or
    // read mapper: a k-mer is only an inverted-index lookup; the full overlap must be exact.
    pub(crate) fn overhangs_with_ids(&self, contig: &[u8]) -> (Vec<Vec<u8>>, Vec<u32>) {
        if contig.len() < K {
            return (Vec::new(), Vec::new());
        }
        // An extending read may overlap up to its own length minus one.
        // Only the final read-length bases can anchor a read that extends
        // the contig; earlier matches cannot contribute a suffix.
        let start = contig
            .len()
            .saturating_sub(self.max_read_len.saturating_sub(1));
        // Two orientations share one bit per original FASTQ read.
        let read_count = self.seqs.len().div_ceil(2);
        let mut used = vec![0u64; read_count.div_ceil(64)];
        let mut ext = Vec::new();
        let mut ids = Vec::new();
        let mut previous = None;
        for q in start..=contig.len() - K {
            let key = rolling_query(contig, q, previous);
            previous = key;
            let Some(key) = key else {
                continue;
            };
            let Some(hits) = self.index.get(&key) else {
                continue;
            };
            // Pathological repetitive k-mers cannot be used as reliable extension anchors.
            if hits.len() > 50000 {
                continue;
            }
            for hit in hits {
                let original = hit.read / 2;
                let word = original as usize / 64;
                let bit = 1u64 << (original as usize % 64);
                if used[word] & bit != 0 {
                    continue;
                }
                let read = &self.seqs[hit.read as usize];
                let Some(extension) = match_hit::matching_suffix(contig, read, q, hit.pos as usize)
                else {
                    continue;
                };
                used[word] |= bit;
                ext.push(extension.to_vec());
                ids.push(original);
            }
        }
        (ext, ids)
    }
}

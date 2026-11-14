use super::{extend, index, scoring, Reads, K};

/// Exploratory read-only recovery after an independently checked cycle cut.
pub(crate) fn try_extend(seq: &[u8], reads: &Reads) -> Option<(Vec<u8>, Vec<u32>)> {
    let (extension, _) = extend(seq.to_vec(), reads, 6, 2);
    if extension.len() <= seq.len() || extension.len() > seq.len() + 8 * reads.max_read_len {
        return None;
    }
    let candidates = [extension.clone()];
    let stats = scoring::count(&candidates, reads, &index::build(&candidates));
    let breadth = stats.coverage[0];
    if breadth * 100 < 90 * extension.len().saturating_sub(K - 1) {
        return None;
    }
    eprintln!(
        "IVANKA_EXPERIMENT_REEXTENDED original={} extended={} supported={}",
        seq.len(),
        extension.len(),
        breadth
    );
    stats
        .depth
        .into_iter()
        .next()
        .map(|depth| (extension, depth))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn no_original_read_evidence_never_fabricates_an_extension() {
        let reads = Reads {
            seqs: Vec::new(),
            index: Default::default(),
            seed_counts: Default::default(),
            max_read_len: 150,
            overlength_rejections: Default::default(),
            overhang_cache: Default::default(),
        };
        assert!(try_extend(&b"ACGT".repeat(750), &reads).is_none());
    }
}

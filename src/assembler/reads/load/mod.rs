use super::dna::{rc, K};
use super::fastq::{mate_headers, FastqSeqReader};
use super::index::build_index;
use super::input::read_open;
use super::types::Reads;
use std::collections::HashMap;
use std::io;

mod pairs;
mod seed_counts;
pub(super) use seed_counts::count_sampled_seed_kmers;
impl Reads {
    pub(crate) fn load(fq1: &str, fq2: &str, max_pairs: Option<usize>) -> io::Result<Self> {
        let (seqs, seed_counts, pairs) = pairs::parse_pairs(fq1, fq2, max_pairs)?;
        eprintln!(
            "building index for {} read pairs ({} oriented sequences)",
            pairs,
            seqs.len()
        );
        let max_read_len = seqs.iter().map(Vec::len).max().unwrap_or(0);
        let index = build_index(&seqs);
        eprintln!(
            "index built: {} keys, {} distinct sampled seed kmers",
            index.len(),
            seed_counts.len()
        );
        Ok(Self {
            seqs,
            index,
            seed_counts,
            max_read_len,
            overhang_cache: Default::default(),
            overlength_rejections: Default::default(),
        })
    }
}

use super::Entry;
use std::fs::File;
use std::io::{self, BufWriter, Write};

/// One complete FASTA replacement; no partially ranked output is exposed.
pub(super) fn write(path: &str, entries: &[Entry]) -> io::Result<()> {
    let mut output = BufWriter::new(File::create(path)?);
    for (header, sequence) in entries {
        output.write_all(header.as_bytes())?;
        output.write_all(b"\n")?;
        output.write_all(sequence)?;
        output.write_all(b"\n")?;
    }
    output.flush()
}

// Apply the unchanged read-backed circular repair and depth trimming to one path.
use super::{circle, island, scoring::Statistics, tiling, Reads, K};

pub(super) fn one(
    contigs: &[Vec<u8>],
    stats: &Statistics,
    reads: &Reads,
    candidate: usize,
) -> Vec<Entry> {
    let repaired = circle::repair(&contigs[candidate], &stats.depth[candidate], reads);
    let (sequence, depth): (&[u8], &[u32]) = match &repaired {
        Some((seq, depths)) => (seq, depths),
        None => (&contigs[candidate], &stats.depth[candidate]),
    };
    let header = format!(">ivanka_{} len={}", candidate + 1, sequence.len());
    if repaired.is_some() {
        eprintln!("IVANKA_READ_BACKED_REOPENED_CYCLE len={}", sequence.len());
    }
    let (start, end) = island::bounds(sequence, depth);
    let clipped = &sequence[start..end];
    let observed = &depth[start..end.saturating_sub(K - 1).max(start)];
    tiling::partition(&header, clipped, observed)
}

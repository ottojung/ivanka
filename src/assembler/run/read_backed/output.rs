use super::{circle, island, scoring::Statistics, tiling, Entry, Reads, K};
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

/// Preserve read-backed components independently: no unobserved joins.
pub(super) fn component(
    contigs: &[Vec<u8>],
    stats: &Statistics,
    reads: &Reads,
    chosen: usize,
) -> Vec<Entry> {
    let repaired = circle::repair(&contigs[chosen], &stats.depth[chosen], reads);
    let (sequence, depth): (&[u8], &[u32]) = match &repaired {
        Some((seq, depths)) => (seq, depths),
        None => (&contigs[chosen], &stats.depth[chosen]),
    };
    if repaired.is_some() {
        eprintln!("IVANKA_READ_BACKED_REOPENED_CYCLE len={}", sequence.len());
    }
    let (start, end) = island::bounds(sequence, depth);
    let observed = &depth[start..end.saturating_sub(K - 1).max(start)];
    let header = format!(">ivanka_{} len={}", chosen + 1, sequence.len());
    tiling::partition(&header, &sequence[start..end], observed)
}

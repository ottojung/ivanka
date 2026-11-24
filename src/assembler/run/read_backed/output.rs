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

// The primary and additional components use the same read-backed presentation
// rule; the former's sequence and ordering are preserved.
pub(super) fn component(
    contigs: &[Vec<u8>],
    reads: &Reads,
    statistics: &Statistics,
    chosen: usize,
) -> Vec<Entry> {
    let repaired = circle::repair(&contigs[chosen], &statistics.depth[chosen], reads);
    let (sequence, depth): (&[u8], &[u32]) = match &repaired {
        Some((seq, depths)) => (seq, depths),
        None => (&contigs[chosen], &statistics.depth[chosen]),
    };
    let header = format!(">ivanka_{} len={}", chosen + 1, sequence.len());
    if repaired.is_some() {
        eprintln!("IVANKA_READ_BACKED_REOPENED_CYCLE len={}", sequence.len());
    }
    let (start, end) = island::bounds(sequence, depth);
    let clipped = &sequence[start..end];
    let observed = &depth[start..end.saturating_sub(K - 1).max(start)];
    eprintln!(
        "IVANKA_READ_BACKED_SELECTION native {} selected [{}] covered_31mers [{}] supporting_pairs [{}] read_support_products [{}]",
        contigs.len(), chosen, statistics.coverage[chosen], statistics.pairs[chosen],
        statistics.coverage[chosen] * statistics.pairs[chosen]
    );
    tiling::partition(&header, clipped, observed)
}

use super::{circle, ranking, scoring::Statistics, tiling, Entry, Reads};
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

// A component with a read-unsubstantiated internal join contributes both
// flanks instead of one bridge. Every rendered piece is a subsequence of the
// native contig; no base is invented across the unsupported interval.
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
    let header = format!(">ivanka_{}", chosen + 1);
    if repaired.is_some() {
        eprintln!("IVANKA_READ_BACKED_REOPENED_CYCLE len={}", sequence.len());
    }
    super::selection(
        contigs.len(),
        chosen,
        statistics.coverage[chosen],
        statistics.pairs[chosen],
    );
    ranking::pieces(depth, sequence.len())
        .into_iter()
        .enumerate()
        .flat_map(|(index, (from, to))| {
            let name = format!("{header} len={}", to - from);
            let name = if index == 0 {
                name
            } else {
                format!("{name}_flank{}", index + 1)
            };
            tiling::present(sequence, depth, (from, to), &name)
        })
        .collect()
}

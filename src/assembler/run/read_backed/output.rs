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

// A read-unsubstantiated internal join is rotated at its unsupported seam:
// both native flanks survive in one contig and no base is invented across it.
pub(super) fn component(
    contigs: &[Vec<u8>],
    reads: &Reads,
    statistics: &Statistics,
    chosen: usize,
) -> Vec<Entry> {
    let native = &contigs[chosen];
    let header = format!(">ivanka_{}", chosen + 1);
    if let Some(join) = ranking::junction(&statistics.depth[chosen], &statistics.spans[chosen]) {
        let (sequence, depth) = ranking::native(native, &statistics.depth[chosen], join);
        let name = format!("{header} len={}", sequence.len());
        return tiling::present(&sequence, &depth, (0, sequence.len()), &name);
    }
    let repaired = circle::repair(native, &statistics.depth[chosen], reads);
    let (sequence, depth): (&[u8], &[u32]) = match &repaired {
        Some((seq, depths)) => (seq, depths),
        None => (native, &statistics.depth[chosen]),
    };
    if repaired.is_some() {
        eprintln!("IVANKA_READ_BACKED_REOPENED_CYCLE len={}", sequence.len());
    }
    let name = format!("{header} len={}", sequence.len());
    tiling::present(sequence, depth, (0, sequence.len()), &name)
}

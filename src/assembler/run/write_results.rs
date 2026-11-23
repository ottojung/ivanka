use super::{read_backed, write_fasta, Reads};
use std::fs::File;
use std::io::{self, BufWriter, Write};

/// The unconfigured MiCall invocation uses the entire read-backed pipeline.
/// Optional research CLI inputs retain the native multi-contig FASTA path.
pub(super) fn write(
    out: &str,
    contigs: &[Vec<u8>],
    reads: &Reads,
    standard: bool,
    skip_matching_seeds: Option<&str>,
) -> io::Result<usize> {
    if standard {
        read_backed::write(out, contigs, reads)
    } else if let Some(path) = skip_matching_seeds.filter(|_| !reads.seqs.is_empty()) {
        let keep = super::seed_duplicates::keep_indices(contigs, path)?;
        let mut output = BufWriter::new(File::create(out)?);
        for &i in &keep {
            let seq = &contigs[i];
            writeln!(output, ">ivanka_{} len={}", i + 1, seq.len())?;
            for chunk in seq.chunks(80) {
                output.write_all(chunk)?;
                output.write_all(b"\n")?;
            }
        }
        output.flush()?;
        Ok(keep.len())
    } else {
        write_fasta(out, contigs)?;
        Ok(contigs.len())
    }
}

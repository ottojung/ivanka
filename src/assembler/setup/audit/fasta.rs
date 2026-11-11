use std::fs::File;
use std::io::{self, BufWriter, Write};
// Preserve the exact original MiCall-facing FASTA formatting.
pub(crate) fn write_fasta(path: &str, contigs: &[Vec<u8>]) -> io::Result<()> {
    let mut output = BufWriter::new(File::create(path)?);
    for (i, seq) in contigs.iter().enumerate() {
        writeln!(output, ">ivanka_{} len={}", i + 1, seq.len())?;
        for chunk in seq.chunks(80) {
            output.write_all(chunk)?;
            output.write_all(b"\n")?;
        }
    }
    output.flush()
}

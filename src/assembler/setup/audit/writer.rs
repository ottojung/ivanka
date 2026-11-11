use super::candidate::local_variants;
use std::collections::HashMap;
use std::fs::OpenOptions;
use std::io::{self, BufWriter, Write};
use std::os::unix::fs::OpenOptionsExt;

pub(crate) fn write_snv_audit(
    path: &str,
    rejected: &[(Vec<u8>, usize)],
    original: &[Vec<u8>],
    sampled: &HashMap<u64, u32>,
    canonical: fn(&[u8]) -> Option<u64>,
) -> io::Result<usize> {
    // create_new never overwrites original FASTQs, MiCall or another audit.
    let stream = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(path)?;
    let mut output = BufWriter::new(stream);
    super::schema::write_header(&mut output)?;
    let variants = local_variants(rejected, original, sampled, canonical);
    for item in &variants {
        writeln!(
            output,
            "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
            item.parent,
            item.length,
            item.pos,
            item.original as char,
            item.alternate as char,
            item.support,
            item.kmer_witnesses,
            item.context
        )?;
    }
    output.flush()?;
    Ok(variants.len())
}

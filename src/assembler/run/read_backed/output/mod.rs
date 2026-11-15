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

mod fragment;
mod pairs;
mod split;
pub(super) use fragment::component;
#[cfg(test)]
pub(super) use fragment::part_header;

pub(super) use pairs::observed;

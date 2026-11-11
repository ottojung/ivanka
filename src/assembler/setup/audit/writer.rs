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
    writeln!(output, "#schema=ivanka.unphased_snv_candidates.v1")?;
    writeln!(
        output,
        "#phasing=unidentified; independent_dna_molecules=false"
    )?;
    writeln!(output,"#sampling=first_50000_pairs_every_third_31mer; kmer_counts_are_occurrences_not_molecules; phred_unchecked=true")?;
    writeln!(output, "#ordinary_micall_fasta_unchanged=true")?;
    writeln!(output,"parent_fasta_index\tlength\tsnv_offset_zero_based\tbaseline_base\talternate_base\tassembling_read_record_support\tnovel_sampled_31mers_ge5\tlocal_61base_unphased_context")?;
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

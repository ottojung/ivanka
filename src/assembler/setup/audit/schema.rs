use std::io::{self, Write};

// The audit schema is separate from the ordinary MiCall contig FASTA.
pub(super) fn write_header<W: Write>(output: &mut W) -> io::Result<()> {
    writeln!(output, "#schema=ivanka.unphased_snv_candidates.v1")?;
    writeln!(
        output,
        "#phasing=unidentified; independent_dna_molecules=false"
    )?;
    writeln!(
        output,
        concat!(
            "#sampling=first_50000_pairs_every_third_31mer; ",
            "kmer_counts_are_occurrences_not_molecules; phred_unchecked=true"
        )
    )?;
    writeln!(output, "#ordinary_micall_fasta_unchanged=true")?;
    writeln!(
        output,
        concat!(
            "parent_fasta_index\tlength\tsnv_offset_zero_based\t",
            "baseline_base\talternate_base\tassembling_read_record_support\t",
            "novel_sampled_31mers_ge5\tlocal_61base_unphased_context"
        )
    )?;
    Ok(())
}

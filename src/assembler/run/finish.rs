use super::{
    append_preserving_diversity, canonical_kmer, select_supported_contigs_read_support,
    select_supported_contigs_with_kmers, write_snv_audit,
};
use std::error::Error;

// Selection uses only read-supported contigs. The ordinary FASTA is
// independent of the evidence-only SNV audit.
pub(super) fn write(
    out: &str,
    max: usize,
    audit_path: Option<&str>,
    standard: bool,
    prepared: super::prepare::Prepared,
) -> Result<usize, Box<dyn Error>> {
    let reads = prepared.reads;
    let contigs = prepared.contigs;
    let supporting_counts = prepared.support;
    let protected_seed_count = prepared.protected;
    let rescue = prepared.rescue;
    let (mut contigs, audit) = if audit_path.is_some() {
        select_supported_contigs_with_kmers(
            contigs,
            supporting_counts,
            max,
            protected_seed_count,
            &reads.seed_counts,
        )
    } else {
        (
            select_supported_contigs_read_support(
                contigs,
                supporting_counts,
                max,
                protected_seed_count,
                &reads.seed_counts,
            ),
            Vec::new(),
        )
    };
    if let Some(rescue) = rescue {
        // Never exceed the cap; replace only a non-protected path whose
        // canonical 31-mers remain represented, else withhold the rescue.
        append_preserving_diversity(&mut contigs, rescue, max, protected_seed_count);
    }
    let count = super::write_results::write(out, &contigs, &reads, standard)?;
    if let Some(path) = audit_path {
        let count = write_snv_audit(&path, &audit, &contigs, &reads.seed_counts, canonical_kmer)?;
        eprintln!(
            "Ivanka separately observed {} unphased SNV alternatives",
            count
        );
    }
    Ok(count)
}

use super::{
    append_preserving_diversity, canonical_kmer, select_supported_contigs,
    select_supported_contigs_with_kmers, write_fasta, write_snv_audit,
};
use std::error::Error;

// Selection uses only read-supported contigs. The ordinary FASTA is
// independent of the optional evidence-only SNV audit, which cannot infer
// an independent molecule or silently modify the selected contigs.
pub(super) fn write(
    out: &str,
    max: usize,
    audit_path: Option<&str>,
    prepared: super::prepare::Prepared,
) -> Result<usize, Box<dyn Error>> {
    let super::prepare::Prepared {
        reads,
        contigs,
        support: supporting_counts,
        protected: protected_seed_count,
        rescue,
    } = prepared;
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
            select_supported_contigs(contigs, supporting_counts, max, protected_seed_count),
            Vec::new(),
        )
    };
    if let Some(rescue) = rescue {
        // Never exceed the user-requested max-contigs cap. Replace only a
        // non-protected path whose canonical 31-mers remain represented;
        // otherwise withhold the rescue to avoid losing distinct evidence.
        append_preserving_diversity(&mut contigs, rescue, max, protected_seed_count);
    }
    super::empty::check(&reads, !contigs.is_empty())?;
    write_fasta(&out, &contigs)?;
    if let Some(path) = audit_path {
        let count = write_snv_audit(&path, &audit, &contigs, &reads.seed_counts, canonical_kmer)?;
        eprintln!(
            "Ivanka separately observed {} unphased SNV alternatives",
            count
        );
    }
    Ok(contigs.len())
}

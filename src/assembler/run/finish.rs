use super::{
    append_preserving_diversity, canonical_kmer, select_supported_contigs_with_kmers,
    write_snv_audit,
};
use std::error::Error;

// Selection always receives the read-sampled k-mer map. Without read evidence
// a suppressed single-SNV neighbour has no audit channel, so a true abundant
// haplotype could be silently lost; the ordinary FASTA stays separate from
// that unphased evidence record.
pub(super) fn write(
    out: &str,
    max: usize,
    audit_path: Option<&str>,
    standard: bool,
    prepared: super::prepare::Prepared,
) -> Result<usize, Box<dyn Error>> {
    let super::prepare::Prepared {
        reads,
        contigs,
        support: supporting_counts,
        protected: protected_seed_count,
        rescue,
    } = prepared;
    let (mut contigs, audit) = select_supported_contigs_with_kmers(
        contigs,
        supporting_counts,
        max,
        protected_seed_count,
        &reads.seed_counts,
    );
    if let Some(rescue) = rescue {
        // Never exceed the user-requested max-contigs cap. Replace only a
        // non-protected path whose canonical 31-mers remain represented;
        // otherwise withhold the rescue to avoid losing distinct evidence.
        append_preserving_diversity(&mut contigs, rescue, max, protected_seed_count);
    }
    let count = super::write_results::write(out, &contigs, &reads, standard)?;
    // The pinned MiCall invocation passes --output but no audit flag. Derive
    // the sidecar from --output so every read-supported suppression decision
    // stays inspectable even in that ordinary invocation.
    let sidecar = audit_path
        .map(str::to_owned)
        .unwrap_or_else(|| format!("{out}.snv_audit.tsv"));
    let observed = write_snv_audit(
        &sidecar,
        &audit,
        &contigs,
        &reads.seed_counts,
        canonical_kmer,
    )?;
    eprintln!("Ivanka separately observed {observed} unphased SNV alternatives");
    Ok(count)
}

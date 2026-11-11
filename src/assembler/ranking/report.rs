pub(super) fn quality(
    reported: usize,
    duplicates: usize,
    no_extension_support: usize,
    variants: usize,
) {
    eprintln!(
        concat!(
            "IVANKA_QUALITY reported={} kmer_redundant={} ",
            "no_extension_support={} snv_audit_candidates={}"
        ),
        reported, duplicates, no_extension_support, variants
    );
}

// A rejected duplicate may still provide independently observed SNV evidence.
pub(super) fn duplicate(
    snv: bool,
    seq: Vec<u8>,
    support: usize,
    variants: &mut Vec<(Vec<u8>, usize)>,
    duplicates: &mut usize,
) {
    if snv {
        variants.push((seq, support));
    } else {
        *duplicates += 1;
    }
}

// Report the exact reasons for suppressing redundant contigs.
pub(super) fn finish(
    retained: Vec<Vec<u8>>,
    variants: Vec<(Vec<u8>, usize)>,
    duplicates: usize,
    no_extension_support: usize,
) -> super::ContigSelection {
    quality(
        retained.len(),
        duplicates,
        no_extension_support,
        variants.len(),
    );
    (retained, variants)
}

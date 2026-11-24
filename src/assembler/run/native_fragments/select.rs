use super::Reads;
use super::{represent, support};
use std::collections::HashSet;
use std::io;

/// Fill unused native contig slots with distinct, read-derived fragments.
///
/// Each added contig is one observed read sequence. No bases are invented and
/// no two observations are joined. Support counts distinct observed pair
/// sequences, not source molecules: identical sequences may come from the
/// same molecule, and the count never claims otherwise. Regions already
/// represented by selected contigs or supplied seeds are skipped, so this
/// only adds evidence for read-supported regions otherwise absent from the
/// native FASTA.
pub(crate) fn retain(
    contigs: &mut Vec<Vec<u8>>,
    reads: &Reads,
    limit: usize,
    supplied: Option<&str>,
) -> io::Result<usize> {
    if contigs.len() >= limit {
        return Ok(0);
    }
    let mut represented = HashSet::new();
    represent::covered(&mut represented, contigs, supplied)?;
    let mut added = 0;
    for (seq, observed_pairs) in support::ranked(reads) {
        if contigs.len() >= limit {
            break;
        }
        if !represent::uncovered(&represented, seq) {
            continue;
        }
        eprintln!(
            "IVANKA_NATIVE_FRAGMENT_RETAINED len={} observed_pairs={} source=original_pair_sequence",
            seq.len(),
            observed_pairs
        );
        represent::cover(&mut represented, seq);
        contigs.push(seq.to_vec());
        added += 1;
    }
    eprintln!(
        "IVANKA_NATIVE_FRAGMENT_TOTAL added={} limit={}",
        added, limit
    );
    Ok(added)
}

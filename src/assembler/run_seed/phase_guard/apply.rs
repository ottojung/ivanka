// All experimental modes are intentionally opt-in and share exact Q15 paired evidence.
use super::{split,mask};
pub(crate) fn apply(contigs: Vec<Vec<u8>>, reads: &[Vec<u8>],
    qualities:&[Vec<u8>], max:usize) -> Vec<Vec<u8>> {
    if std::env::var("IVANKA_EXPERIMENTAL_PHASE_SPLIT").as_deref()==Ok("1") {
        split::split_unsupported_contigs(contigs,reads,qualities,max)
    } else if std::env::var("IVANKA_EXPERIMENTAL_PHASE_MASK").as_deref()==Ok("1") {
        eprintln!("EXPERIMENTAL_PHASE_MASK warning: N may be replaced by MiCall remap consensus; do not interpret downstream results as phase-safe");
        mask::mask_unsupported_contigs(contigs,reads,qualities)
    } else {
        split::audit_unsupported_contigs(&contigs,reads,qualities);
        contigs
    }
}

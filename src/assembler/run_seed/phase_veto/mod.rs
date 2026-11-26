mod dedup;
mod detect;
mod evidence;
mod filter;
mod filter_aux;
mod scan;
#[cfg(test)]
mod tests;
mod verdict;

use evidence::Prep;
pub(crate) use filter::reject_with;
pub(crate) use filter_aux::vet_rescue_with;
#[cfg(test)]
pub(crate) use filter_aux::{reject_unsupported_recombinants, vet_rescue};

// Read-derived evidence is computed once per invocation and shared by the
// contig veto and the rescue veto; neither step mutates it.
pub(crate) struct Evidence {
    preps: Vec<Prep>,
    sigs: Vec<u32>,
}

pub(crate) fn prepare(reads: &[Vec<u8>], quals: &[Vec<u8>]) -> Evidence {
    Evidence {
        preps: evidence::make_preps(reads, quals),
        sigs: evidence::signature_ids(reads),
    }
}

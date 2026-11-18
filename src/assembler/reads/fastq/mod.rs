mod id;
#[cfg(test)]
mod test_reader;
pub(super) use id::mate_headers;
#[cfg(test)]
mod pair_tests;
#[cfg(test)]
use super::types::Reads;

mod reader;
pub(crate) use reader::FastqSeqReader;

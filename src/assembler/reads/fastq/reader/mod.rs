use std::io::BufRead;

pub(crate) struct FastqSeqReader<R: BufRead> {
    reader: R,
    pub(crate) header: String,
    bases: String,
    plus: String,
    quality: String,
}
impl<R: BufRead> FastqSeqReader<R> {
    pub(crate) fn new(reader: R) -> Self {
        Self {
            reader,
            header: String::new(),
            bases: String::new(),
            plus: String::new(),
            quality: String::new(),
        }
    }
}
mod record;

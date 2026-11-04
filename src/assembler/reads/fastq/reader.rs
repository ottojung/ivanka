use std::io::{self,BufRead};
pub(crate) struct FastqSeqReader<R: BufRead> {
    reader: R,
    pub(crate) header: String,
    bases: String,
    plus: String,
    quality: String,
}
impl<R: BufRead> FastqSeqReader<R> {
    pub(crate) fn new(reader: R) -> Self {
        Self {reader, header:String::new(), bases:String::new(),
            plus:String::new(), quality:String::new()}
    }
    pub(crate) fn qualities(&self) -> &[u8] {
        self.quality.trim_end().as_bytes()
    }
    pub(crate) fn read_seq(&mut self) -> io::Result<Option<Vec<u8>>> {
        self.header.clear();self.bases.clear();self.plus.clear();self.quality.clear();
        if self.reader.read_line(&mut self.header)?==0 {return Ok(None);}
        if !self.header.starts_with('@') {
            return Err(io::Error::new(io::ErrorKind::InvalidData,"invalid FASTQ header"));
        }
        if self.reader.read_line(&mut self.bases)?==0 {
            return Err(io::Error::new(io::ErrorKind::UnexpectedEof,"missing bases"));
        }
        if self.reader.read_line(&mut self.plus)?==0 || !self.plus.starts_with('+')
            || self.reader.read_line(&mut self.quality)?==0 {
            return Err(io::Error::new(io::ErrorKind::InvalidData,"invalid FASTQ record"));
        }
        let seq=self.bases.trim_end().as_bytes().iter()
            .map(|b|b.to_ascii_uppercase()).collect::<Vec<_>>();
        if seq.len()!=self.quality.trim_end().len() {
            return Err(io::Error::new(io::ErrorKind::InvalidData,"bases / qualities differ"));
        }
        Ok(Some(seq))
    }
}

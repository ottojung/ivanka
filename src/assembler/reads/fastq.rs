use std::io::{self, BufRead};
pub(crate) fn fastq_seq(r: &mut dyn BufRead) -> io::Result<Option<Vec<u8>>> {
    let mut a=String::new();
    let mut b=String::new();
    if r.read_line(&mut a)? == 0 { return Ok(None); }
    if !a.starts_with('@') { return Err(io::Error::new(io::ErrorKind::InvalidData,"invalid FASTQ header")); }
    if r.read_line(&mut b)? == 0 { return Err(io::Error::new(io::ErrorKind::UnexpectedEof,"missing bases")); }
    let mut plus=String::new();
    let mut qual=String::new();
    if r.read_line(&mut plus)? == 0 || !plus.starts_with('+') || r.read_line(&mut qual)? == 0 {
        return Err(io::Error::new(io::ErrorKind::InvalidData,"invalid FASTQ record"));
    }
    let seq=b.trim_end().as_bytes().iter().map(|b| b.to_ascii_uppercase()).collect::<Vec<_>>();
    if seq.len()!=qual.trim_end().len() {return Err(io::Error::new(io::ErrorKind::InvalidData,"bases / qualities differ"));}
    Ok(Some(seq))
}

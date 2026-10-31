
use flate2::read::MultiGzDecoder;
use std::fs::File;
use std::io::{self, BufRead, BufReader};

pub(crate) fn read_open(path: &str) -> io::Result<Box<dyn BufRead>> {
    let f = File::open(path)?;
    if path.ends_with(".gz") {
        Ok(Box::new(BufReader::new(MultiGzDecoder::new(f))))
    } else { Ok(Box::new(BufReader::new(f))) }
}
// G2P-derived MiCall seed contigs. These seed candidates are supplied before
// assembly; this does not require any reference mapping or coordinate lookup.
pub(crate) fn fasta_seeds(path: &str) -> io::Result<Vec<Vec<u8>>> {
    let mut output = Vec::new();
    let mut current = Vec::new();
    let mut started = false;
    for line in read_open(path)?.lines() {
        let line = line?;
        if line.starts_with('>') {
            if started && !current.is_empty() {
                if current.iter().all(|b| matches!(b, b'A'|b'C'|b'G'|b'T')) {
                    output.push(std::mem::take(&mut current));
                } else {current.clear();}
            }
            started = true;
        } else {
            if !started && !line.trim().is_empty() {
                return Err(io::Error::new(io::ErrorKind::InvalidData, "sequence before FASTA header"));
            }
            current.extend(line.trim().bytes().map(|b| b.to_ascii_uppercase()));
        }
    }
    if started && !current.is_empty() && current.iter().all(|b| matches!(b, b'A'|b'C'|b'G'|b'T')) {
        output.push(current);
    }
    Ok(output)
}
pub(crate) fn fastq_seq(r: &mut dyn BufRead) -> io::Result<Option<Vec<u8>>> {
    let mut a=String::new(); let mut b=String::new();
    if r.read_line(&mut a)? == 0 { return Ok(None); }
    if !a.starts_with('@') { return Err(io::Error::new(io::ErrorKind::InvalidData,"invalid FASTQ header")); }
    if r.read_line(&mut b)? == 0 { return Err(io::Error::new(io::ErrorKind::UnexpectedEof,"missing bases")); }
    let mut plus=String::new(); let mut qual=String::new();
    if r.read_line(&mut plus)? == 0 || !plus.starts_with('+') || r.read_line(&mut qual)? == 0 {
        return Err(io::Error::new(io::ErrorKind::InvalidData,"invalid FASTQ record"));
    }
    let seq=b.trim_end().as_bytes().iter().map(|b| b.to_ascii_uppercase()).collect::<Vec<_>>();
    if seq.len()!=qual.trim_end().len() {return Err(io::Error::new(io::ErrorKind::InvalidData,"bases / qualities differ"));}
    Ok(Some(seq))
}

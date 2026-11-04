use super::{read_open,FastqSeqReader,mate_headers};
use std::io::{self,ErrorKind};
fn error(message: &'static str) -> io::Error {
    io::Error::new(ErrorKind::InvalidData,message)
}
// Never retain quality arrays or reopen FASTQs in ordinary assembly.
pub(crate) fn load_phase_qualities_if_optin(a:&str,b:&str,
    limit:Option<usize>,seqs:&[Vec<u8>]) -> io::Result<Option<Vec<Vec<u8>>>> {
    let enabled=["IVANKA_EXPERIMENTAL_PHASE_AUDIT",
        "IVANKA_EXPERIMENTAL_PHASE_MASK","IVANKA_EXPERIMENTAL_PHASE_SPLIT"]
        .iter().any(|name|std::env::var(name).as_deref()==Ok("1"));
    if !enabled {return Ok(None);}
    Ok(Some(load_phase_qualities(a,b,limit,seqs)?))
}
pub(super) fn load_phase_qualities(a:&str,b:&str,
    limit:Option<usize>,seqs:&[Vec<u8>]) -> io::Result<Vec<Vec<u8>>> {
    let mut r1=FastqSeqReader::new(read_open(a)?);
    let mut r2=FastqSeqReader::new(read_open(b)?);
    let mut qualities=Vec::new();
    loop {
        if limit.is_some_and(|n|qualities.len()/4>=n) {break;}
        let (x,y)=(r1.read_seq()?,r2.read_seq()?);
        if x.is_none()!=y.is_none() {return Err(error("unequal FASTQ mate counts"));}
        let (Some(x),Some(y))=(x,y) else {break;};
        if seqs.get(qualities.len()).map(Vec::as_slice)!=Some(x.as_slice())
            || seqs.get(qualities.len()+2).map(Vec::as_slice)!=Some(y.as_slice()) {
            return Err(error("FASTQ bases changed between assembly and phase audit"));
        }
        if !mate_headers(&r1.header,&r2.header) {return Err(error("FASTQ pair IDs disagree"));}
        for qual in [r1.qualities(),r2.qualities()] {
            if !qual.iter().all(|&q|(33..=126).contains(&q)) {
                return Err(error("invalid FASTQ Phred+33 quality character"));
            }
            qualities.push(qual.to_vec());
            qualities.push(qual.iter().rev().copied().collect());
        }
    }
    if qualities.len()!=seqs.len() {
        return Err(error("FASTQ quality and assembled read counts differ"));
    }
    Ok(qualities)
}

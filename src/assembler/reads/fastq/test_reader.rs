use super::FastqSeqReader;
#[test]
fn fastq_reuses_buffers_without_changing_records() {
    use std::io::{Cursor, ErrorKind};
    let mut reader = FastqSeqReader::new(Cursor::new(
        b"@first\nacgTn \n+\n!!!!!\n@second\nGGGG\n+\n####\n".as_slice(),
    ));
    assert_eq!(reader.read_seq().unwrap().unwrap(), b"ACGTN");
    let first_capacity = reader.header.capacity();
    assert_eq!(reader.read_seq().unwrap().unwrap(), b"GGGG");
    assert!(reader.header.capacity() >= first_capacity);
    assert!(reader.read_seq().unwrap().is_none());
    let mut invalid = FastqSeqReader::new(Cursor::new(b"@x\nACGT\n+\n!!!\n".as_slice()));
    assert_eq!(
        invalid.read_seq().unwrap_err().kind(),
        ErrorKind::InvalidData
    );
}

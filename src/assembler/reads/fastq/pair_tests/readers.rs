use super::*;

#[test]
fn rejects_records_when_second_mate_file_reorders() {
    let a = b"@a 1:N:0:7\nAAAA\n+\n!!!!\n@b 1:N:0:7\nAAAA\n+\n!!!!\n";
    let b = b"@a 2:N:0:7\nCCCC\n+\n!!!!\n@c 2:N:0:7\nCCCC\n+\n!!!!\n";
    let mut r1 = FastqSeqReader::new(Cursor::new(a));
    let mut r2 = FastqSeqReader::new(Cursor::new(b));
    r1.read_seq().unwrap();
    r2.read_seq().unwrap();
    assert!(mate_headers(&r1.header, &r2.header));
    r1.read_seq().unwrap();
    r2.read_seq().unwrap();
    assert!(!mate_headers(&r1.header, &r2.header));
}

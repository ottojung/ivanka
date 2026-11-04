use super::mate_headers;
use super::{FastqSeqReader, Reads};
use std::{fs, io::{Cursor, ErrorKind}};

#[test] fn casava_and_legacy_mates_must_match() {
    assert!(mate_headers("@instrument:42 1:N:0:48\n",
                         "@instrument:42 2:N:0:48\n"));
    assert!(mate_headers("@read/1", "@read/2"));
    assert!(mate_headers("@same", "@same"));
    assert!(!mate_headers("@one 1:N:0:1", "@two 2:N:0:1"));
    assert!(!mate_headers("@same/2", "@same/1"));
    assert!(!mate_headers("@same/1 2:N:0:1", "@same/2 2:N:0:1"));
    assert!(!mate_headers("@same 1:N:0:1", "@same"));
    assert!(!mate_headers("@same 1:N:0:1", "@same 1:N:0:1"));
    assert!(!mate_headers("@", "@"));
}

#[test] fn rejects_records_when_second_mate_file_reorders() {
    let a=b"@a 1:N:0:7\nAAAA\n+\n!!!!\n@b 1:N:0:7\nAAAA\n+\n!!!!\n";
    let b=b"@a 2:N:0:7\nCCCC\n+\n!!!!\n@c 2:N:0:7\nCCCC\n+\n!!!!\n";
    let mut r1=FastqSeqReader::new(Cursor::new(a));
    let mut r2=FastqSeqReader::new(Cursor::new(b));
    r1.read_seq().unwrap();r2.read_seq().unwrap();
    assert!(mate_headers(&r1.header,&r2.header));
    r1.read_seq().unwrap();r2.read_seq().unwrap();
    assert!(!mate_headers(&r1.header,&r2.header));
}

#[test] fn reordered_pairs_fail_during_actual_load() {
    let d=std::env::temp_dir();
    let a=d.join(format!("ivanka-verified-r1-{}.fastq",std::process::id()));
    let b=d.join(format!("ivanka-verified-r2-{}.fastq",std::process::id()));
    fs::write(&a,b"@read-a 1:N:0:1\nACGT\n+\n!!!!\n@read-b 1:N:0:1\nACGT\n+\n!!!!\n").unwrap();
    fs::write(&b,b"@read-a 2:N:0:1\nTGCA\n+\n!!!!\n@read-c 2:N:0:1\nTGCA\n+\n!!!!\n").unwrap();
    let result=Reads::load(a.to_str().unwrap(),b.to_str().unwrap(),None);
    fs::remove_file(a).unwrap();fs::remove_file(b).unwrap();
    let err=result.err().expect("mismatched original pair must be rejected");
    assert_eq!(err.kind(),ErrorKind::InvalidData);
    assert!(err.to_string().contains("read-pair IDs"));
}

use super::*;

#[test]
fn casava_and_legacy_mates_must_match() {
    assert!(mate_headers(
        "@instrument:42 1:N:0:48\n",
        "@instrument:42 2:N:0:48\n"
    ));
    assert!(mate_headers("@read/1", "@read/2"));
    assert!(mate_headers("@same", "@same"));
    assert!(!mate_headers("@one 1:N:0:1", "@two 2:N:0:1"));
    assert!(!mate_headers("@same/2", "@same/1"));
    assert!(!mate_headers("@same/1 2:N:0:1", "@same/2 2:N:0:1"));
    assert!(!mate_headers("@same 1:N:0:1", "@same"));
    assert!(!mate_headers("@same 1:N:0:1", "@same 1:N:0:1"));
    assert!(!mate_headers("@", "@"));
}

#[test]
fn sra_header_metadata_preserves_pair_identity() {
    assert!(mate_headers(
        "@SRR123.1 1 length=250",
        "@SRR123.1 2 length=250"
    ));
    assert!(mate_headers(
        "@SRR123.1 1 length=250",
        "@SRR123.1 1 length=250"
    ));
    assert!(mate_headers(
        "@SRR123.1 250 length=250",
        "@SRR123.1 250 length=250"
    ));
    assert!(!mate_headers(
        "@SRR123.1 1 length=250",
        "@SRR124.1 2 length=250"
    ));
    assert!(!mate_headers(
        "@SRR123.1 1 length=250",
        "@SRR123.2 2 length=250"
    ));
}

#[test]
fn invalid_casava_mate_numbers_remain_rejected() {
    assert!(!mate_headers("@x 3:N:0:A", "@x 2:N:0:A"));
    assert!(!mate_headers("@x 1:N:0:A", "@x 3:N:0:A"));
    assert!(!mate_headers("@x/2 1:N:0:A", "@x/1 2:N:0:A"));
}

use super::finish::write;
use super::prepare::Prepared;
use super::test_finish::{reads, Dir};
use super::test_finish_seq::{path, sampled};

// Fail-closed probe for the empty-map case: production must always supply the
// read-sampled map. With that map a >=128 nt high-support single-SNV neighbour
// is recorded in the derived sidecar instead of being silently discarded. The
// empty-map wrapper is test-only, so no production call can take that path.
#[test]
fn empty_map_path_cannot_silently_suppress_a_read_supported_haplotype() {
    let major = path(0x0bad_c0de_0000_0001, 310);
    let mut minor = major.clone();
    minor[100] = if minor[100] == b'A' { b'C' } else { b'A' };
    let dir = Dir::new();
    let out = dir.out();
    let prepared = Prepared {
        reads: reads(sampled(&minor)),
        contigs: vec![major, minor],
        support: vec![300, 120],
        protected: 0,
        rescue: None,
    };
    write(&out, 16, None, false, prepared).unwrap();
    let sidecar = std::fs::read_to_string(format!("{out}.snv_audit.tsv")).unwrap();
    assert!(
        sidecar.lines().any(|line| line.contains("\t100\t")),
        "empty sampled map would silently lose a true read-supported haplotype"
    );
}

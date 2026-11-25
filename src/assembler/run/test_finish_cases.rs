use super::finish::write;
use super::prepare::Prepared;
use super::test_finish::{reads, Dir};
use super::test_finish_seq::{fasta_seqs, path, sampled};

// A read-supported >=128 nt single-SNV neighbour is suppressed from the
// ordinary FASTA but preserved in the sidecar derived from --output. This is
// fail-closed: regressing production to the empty-map selector empties the
// sidecar and fails this test.
#[test]
fn derived_sidecar_records_read_supported_hamming1_alternative() {
    let major = path(0x1234_5678_9abc_def0, 310);
    let mut minor = major.clone();
    minor[155] = if minor[155] == b'A' { b'C' } else { b'A' };
    let dir = Dir::new();
    let out = dir.out();
    let prepared = Prepared {
        reads: reads(sampled(&minor)),
        contigs: vec![major, minor],
        support: vec![300, 150],
        protected: 0,
        rescue: None,
    };
    assert_eq!(write(&out, 16, None, false, prepared).unwrap(), 1);
    let text = std::fs::read_to_string(format!("{out}.snv_audit.tsv")).unwrap();
    assert!(text.starts_with("#schema=ivanka.unphased_snv_candidates.v1\n"));
    assert!(
        text.contains("\t155\t"),
        "SNV decision lost without read map"
    );
}

// Negative test: true diverse haplotypes and caller-supplied seeds survive
// even when a protected seed has a Hamming-1 neighbour with read evidence.
#[test]
fn diverse_haplotypes_and_supplied_seeds_survive_with_read_evidence() {
    let seed = path(0xfeed_face_cafe_beef, 310);
    let mut variant = seed.clone();
    variant[200] = if variant[200] == b'A' { b'G' } else { b'A' };
    let other = path(0x0bad_c0de_dead_beef, 310);
    let dir = Dir::new();
    let out = dir.out();
    let prepared = Prepared {
        reads: reads(sampled(&variant)),
        contigs: vec![seed.clone(), variant, other.clone()],
        support: vec![300, 150, 120],
        protected: 1,
        rescue: None,
    };
    assert_eq!(write(&out, 16, None, false, prepared).unwrap(), 2);
    let kept = fasta_seqs(&std::fs::read_to_string(&out).unwrap());
    assert!(
        kept.contains(&seed) && kept.contains(&other),
        "seed or haplotype suppressed"
    );
}

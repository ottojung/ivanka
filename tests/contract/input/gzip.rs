use super::{fixture, Fixture};
use std::io::Write;

#[test]
fn gzipped_inputs_match_plain_inputs() {
    let case = Fixture::new();
    let mut paths = Vec::new();
    for mate in 1..=2 {
        let bytes = std::fs::read(fixture(&format!("a_R{mate}.fastq"))).unwrap();
        let path = case.path(&format!("r{mate}.fastq.gz"));
        let file = std::fs::File::create(&path).unwrap();
        let mut gz = flate2::write::GzEncoder::new(file, flate2::Compression::default());
        gz.write_all(&bytes).unwrap();
        gz.finish().unwrap();
        paths.push(path);
    }
    assert!(case.run_paths(&paths[0], &paths[1], &[]).status.success());
    assert_eq!(
        case.output(),
        std::fs::read(fixture("a_expected.fa")).unwrap()
    );
}

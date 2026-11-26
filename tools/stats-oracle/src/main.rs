//! Standalone provenance oracle for the PR #466 packed/byte-key equivalence
//! claim. Test-only: no production Ivanka code is linked or modified.
mod byte;
mod dump;
mod fixture;
mod packed;
mod sha256;

use dump::{EXPECTED_BYTES, EXPECTED_FASTA, EXPECTED_STATS};

fn arg(name: &str, default: &str) -> String {
    let args: Vec<String> = std::env::args().collect();
    args.iter()
        .position(|a| a == name)
        .and_then(|i| args.get(i + 1))
        .cloned()
        .unwrap_or_else(|| default.to_string())
}

const VENDORED: [(&str, &[u8]); 13] = [
    (
        "732b64ca/packed/index/mod.rs",
        include_bytes!("packed/index/mod.rs"),
    ),
    (
        "732b64ca/packed/index/build.rs",
        include_bytes!("packed/index/build.rs"),
    ),
    (
        "732b64ca/packed/index/canon.rs",
        include_bytes!("packed/index/canon.rs"),
    ),
    (
        "732b64ca/packed/scoring/mod.rs",
        include_bytes!("packed/scoring/mod.rs"),
    ),
    (
        "732b64ca/packed/scoring/accumulate.rs",
        include_bytes!("packed/scoring/accumulate.rs"),
    ),
    (
        "732b64ca/packed/scoring/scan.rs",
        include_bytes!("packed/scoring/scan.rs"),
    ),
    (
        "732b64ca/packed/scoring/statistics.rs",
        include_bytes!("packed/scoring/statistics.rs"),
    ),
    (
        "47ee44c2/byte/index/mod.rs",
        include_bytes!("byte/index/mod.rs"),
    ),
    (
        "47ee44c2/byte/index/build.rs",
        include_bytes!("byte/index/build.rs"),
    ),
    (
        "47ee44c2/byte/scoring/mod.rs",
        include_bytes!("byte/scoring/mod.rs"),
    ),
    (
        "47ee44c2/byte/scoring/accumulate.rs",
        include_bytes!("byte/scoring/accumulate.rs"),
    ),
    (
        "47ee44c2/byte/scoring/scan.rs",
        include_bytes!("byte/scoring/scan.rs"),
    ),
    (
        "47ee44c2/byte/scoring/statistics.rs",
        include_bytes!("byte/scoring/statistics.rs"),
    ),
];

fn main() {
    let mode = arg("--fixture", "lcg");
    let order: [usize; 4] = arg("--order", "0,1,2,3")
        .split(',')
        .map(|s| s.parse().unwrap())
        .collect::<Vec<_>>()
        .try_into()
        .unwrap();
    let big = arg("--endian", "le") == "be";
    let (contigs, seqs) = fixture::build(&mode);
    let packed = packed::count(&contigs, &packed::Reads { seqs: seqs.clone() });
    let reference = byte::count(&contigs, &byte::Reads { seqs: seqs.clone() });
    assert_eq!(packed, reference, "packed and byte-key stats differ");
    let dump = dump::serialize(&packed, order, big);
    let fasta = dump::fasta(&contigs);
    let stats_hash = sha256::digest(&dump);
    let fasta_hash = sha256::digest(&fasta);
    println!(
        "fixture={mode} order={order:?} endian={}",
        if big { "be" } else { "le" }
    );
    println!(
        "contigs=6x8000 pairs=80000x250 depth_loci={}",
        packed.0.iter().map(Vec::len).sum::<usize>()
    );
    println!(
        "dump_bytes={} expected={} match={}",
        dump.len(),
        EXPECTED_BYTES,
        dump.len() == EXPECTED_BYTES
    );
    println!("stats_sha256={stats_hash}");
    println!("fasta_sha256={fasta_hash}");
    println!(
        "expected_stats_sha256={EXPECTED_STATS} match={}",
        stats_hash == EXPECTED_STATS
    );
    println!(
        "expected_fasta_sha256={EXPECTED_FASTA} match={}",
        fasta_hash == EXPECTED_FASTA
    );
    if let Some(dir) = std::env::args().skip_while(|a| a != "--out").nth(1) {
        std::fs::write(std::path::Path::new(&dir).join("packed-stats.bin"), &dump).unwrap();
        std::fs::write(
            std::path::Path::new(&dir).join("fixture-contigs.fasta"),
            &fasta,
        )
        .unwrap();
        println!("wrote {dir}/packed-stats.bin and {dir}/fixture-contigs.fasta");
    }
    if std::env::args().any(|a| a == "--vendor-hashes") {
        for (name, bytes) in VENDORED {
            println!(
                "vendor {name} bytes={} sha256={}",
                bytes.len(),
                sha256::digest(bytes)
            );
        }
    }
    let verify = arg("--verify-file", "");
    if !verify.is_empty() {
        let bytes = std::fs::read(&verify).expect("--verify-file must name a readable artifact");
        let h = sha256::digest(&bytes);
        println!(
            "verify_file={verify} bytes={} sha256={h} literal_match={}",
            bytes.len(),
            h == EXPECTED_STATS
        );
    }
    if std::env::args().any(|a| a == "--scan-framings") {
        let permutations = [
            [0, 1, 2, 3],
            [0, 1, 3, 2],
            [0, 2, 1, 3],
            [0, 2, 3, 1],
            [0, 3, 1, 2],
            [0, 3, 2, 1],
            [1, 0, 2, 3],
            [1, 0, 3, 2],
            [1, 2, 0, 3],
            [1, 2, 3, 0],
            [1, 3, 0, 2],
            [1, 3, 2, 0],
            [2, 0, 1, 3],
            [2, 0, 3, 1],
            [2, 1, 0, 3],
            [2, 1, 3, 0],
            [2, 3, 0, 1],
            [2, 3, 1, 0],
            [3, 0, 1, 2],
            [3, 0, 2, 1],
            [3, 1, 0, 2],
            [3, 1, 2, 0],
            [3, 2, 0, 1],
            [3, 2, 1, 0],
        ];
        for big in [false, true] {
            for o in permutations {
                let h = sha256::digest(&dump::serialize(&packed, o, big));
                println!(
                    "framing order={o:?} endian={} sha256={h} literal={}",
                    if big { "be" } else { "le" },
                    h == EXPECTED_STATS
                );
            }
        }
    }
}

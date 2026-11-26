use super::{canonical, keep_indices, rc};

#[test]
fn reverse_complemented_sequences_share_the_same_exact_key() {
    let seq = b"ACGGTCTGCTTCAATGTCGGCAAGTACTAGG";
    assert_eq!(canonical(seq), canonical(&rc(seq)));
}

#[test]
fn remove_exact_seed_copies_but_retain_distinct_native_haplotypes() {
    let seed = b"ACGGTCTGCTTCAATGTCGGCAAGTACTAGG";
    let distinct = b"ACGGTCTGCTTCAATGTCGGCAAGTACTAGA";
    let path = std::env::temp_dir().join(format!("ivanka-seed-novel-{}.fa", std::process::id()));
    std::fs::write(
        &path,
        [
            b">seed
"
            .as_slice(),
            seed,
            b"
",
        ]
        .concat(),
    )
    .unwrap();
    let contigs = vec![seed.to_vec(), distinct.to_vec(), rc(seed)];
    let kept = keep_indices(&contigs, path.to_str().unwrap()).unwrap();
    std::fs::remove_file(path).unwrap();
    assert_eq!(
        kept,
        vec![1],
        "only exact or RC-exact seed copies may be omitted"
    );
}

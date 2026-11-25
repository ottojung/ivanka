use super::*;

fn path(seed: u64, len: usize) -> Vec<u8> {
    let mut x = seed;
    (0..len)
        .map(|_| {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            b"ACGT"[(x & 3) as usize]
        })
        .collect()
}

// A single substitution removes K canonical windows regardless of contig
// length. The old ratio rule kept it on short contigs and moved it to the
// audit on long ones; selection must not depend on assembled length.
#[test]
fn short_single_substitution_neighbour_is_deduplicated_like_long_one() {
    let major = path(0x1234_5678_9abc_def0, 310);
    let mut minor = major.clone();
    minor[155] = if minor[155] == b'A' { b'C' } else { b'A' };
    let kept = select_supported_contigs(vec![major, minor], vec![300, 140], 16, 0);
    assert_eq!(kept.len(), 1, "one substitution is not a second contig");
}

// Negative test for any future blanket threshold change: distinct haplotypes
// and caller-supplied seeds must survive even alongside near-duplicates.
#[test]
fn diverse_haplotypes_and_protected_seeds_survive() {
    let seed = path(0xfeed_face_cafe_beef, 310);
    let mut seed_variant = seed.clone();
    seed_variant[200] = b'G';
    let other = path(0x0bad_c0de_dead_beef, 310);
    let kept = select_supported_contigs(
        vec![seed.clone(), seed_variant, other.clone()],
        vec![300, 150, 120],
        16,
        1,
    );
    assert_eq!(kept[0], seed, "protected seed kept despite SNV neighbour");
    assert!(kept.contains(&other), "distinct haplotype kept");
    assert_eq!(kept.len(), 2);
}

// A genuinely novel short contig shares no windows; the absolute budget must
// not silently discard it as a duplicate.
#[test]
fn novel_short_contig_is_not_deduplicated() {
    let major = path(7, 310);
    let novel = path(99, 31);
    let kept = select_supported_contigs(vec![major, novel.clone()], vec![300, 90], 16, 0);
    assert!(kept.contains(&novel));
}

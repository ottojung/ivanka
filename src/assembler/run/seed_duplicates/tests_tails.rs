//! Adversarial cases distilled from read-only frozen/adverse-tail audits.
use super::{keep_indices, rc};
use std::io::Write;
use std::sync::atomic::{AtomicUsize, Ordering};

static NEXT: AtomicUsize = AtomicUsize::new(0);

fn seq(len: usize, phase: usize) -> Vec<u8> {
    (0..len).map(|i| b"ACGT"[(i + phase) % 4]).collect()
}

fn keep(seeds: &[&[u8]], contigs: &[Vec<u8>]) -> Vec<usize> {
    let id = NEXT.fetch_add(1, Ordering::Relaxed);
    let path = std::env::temp_dir().join(format!("ivanka-t-{id}-{}.fa", std::process::id()));
    let mut file = std::fs::File::create(&path).unwrap();
    for (index, seed) in seeds.iter().enumerate() {
        writeln!(file, ">s{index}").unwrap();
        file.write_all(seed).unwrap();
        writeln!(file).unwrap();
    }
    drop(file);
    let kept = keep_indices(contigs, path.to_str().unwrap()).unwrap();
    std::fs::remove_file(&path).unwrap();
    kept
}

#[test]
fn exact_seed_copies_removed_minority_retained() {
    let dominant = seq(324, 0);
    let weak = seq(306, 2);
    let mut minority = weak.clone();
    minority[80] = if minority[80] == b'A' { b'C' } else { b'A' };
    let contigs = [dominant.clone(), weak.clone(), minority];
    assert_eq!(keep(&[&dominant, &weak], &contigs), vec![2]);
}

#[test]
fn reverse_complement_exact_copy_is_removed_without_touching_near_duplicate() {
    let dominant = seq(318, 1);
    let reverse = rc(&dominant);
    let mut near = dominant.clone();
    near[17] = if near[17] == b'A' { b'C' } else { b'A' };
    let contigs = [dominant.clone(), reverse, near];
    assert_eq!(keep(&[&dominant], &contigs), vec![2]);
}

#[test]
fn abundant_minority_and_recombinant_are_never_suppressed() {
    let major = seq(300, 0);
    let mut minority = major.clone();
    minority[150] = if minority[150] == b'A' { b'C' } else { b'A' };
    let mut recombinant = major[..150].to_vec();
    recombinant.extend_from_slice(&seq(150, 3));
    let contigs = [major.clone(), minority, recombinant];
    assert_eq!(keep(&[&major], &contigs), vec![1, 2]);
}

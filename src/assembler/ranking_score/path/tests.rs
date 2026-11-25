use super::*;
fn k(w: &[u8]) -> Option<u64> {
    // Synthetic fixture identity: production uses 2-bit canonical k-mers, but
    // this hash only needs distinct window keys. Wrapping makes debug builds
    // agree with the release-mode arithmetic this fixture was written for.
    Some(
        w.iter()
            .fold(0u64, |v, &b| v.wrapping_mul(5).wrapping_add(b as u64)),
    )
}
fn keys(s: &[u8]) -> HashSet<u64> {
    s.windows(K).filter_map(k).collect()
}
fn evidence(s: &[u8], rep: &HashSet<u64>, n: u32) -> HashMap<u64, u32> {
    keys(s).difference(rep).map(|&k| (k, n)).collect()
}
fn variant(blocks: &[(usize, usize)]) -> Vec<u8> {
    let mut s = vec![b'A'; 300];
    for &(a, b) in blocks {
        s[a..b].fill(b'C');
    }
    s
}
fn ok(s: &[u8], rep: &HashSet<u64>, c: &HashMap<u64, u32>, n: usize) -> bool {
    supported_path_alternative(s, n, rep, c, k)
}
#[test]
fn phased_islands_supported() {
    let rep = keys(&vec![b'A'; 300]);
    let long = variant(&[(100, 170)]);
    assert!(ok(&long, &rep, &evidence(&long, &rep, 10), 200));
    let split = variant(&[(100, 140), (180, 220)]);
    assert!(ok(&split, &rep, &evidence(&split, &rep, 10), 200));
}
#[test]
fn single_snv_and_unsampled_rejected() {
    let rep = keys(&vec![b'A'; 300]);
    let one = variant(&[(100, 101)]);
    assert!(!ok(&one, &rep, &evidence(&one, &rep, 10), 200));
    let alt = variant(&[(100, 170)]);
    assert!(!ok(&alt, &rep, &HashMap::new(), 200));
    assert!(!ok(&alt, &rep, &evidence(&alt, &rep, 10), 1));
}
#[test]
fn terminal_tail_rejected() {
    let rep = keys(&vec![b'A'; 300]);
    let tail = variant(&[(0, 70)]);
    assert!(!ok(&tail, &rep, &evidence(&tail, &rep, 10), 200));
}

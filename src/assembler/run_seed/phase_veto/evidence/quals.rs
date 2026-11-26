use super::encode::kcodes;
use super::{Prep, A, Q15};

fn lowq(q: &[u8]) -> Vec<usize> {
    let mut o = vec![0; q.len() + 1];
    for (i, &x) in q.iter().enumerate() {
        o[i + 1] = o[i] + usize::from(x < Q15);
    }
    o
}

pub(crate) fn make_preps(reads: &[Vec<u8>], quals: &[Vec<u8>]) -> Vec<Prep> {
    reads
        .iter()
        .zip(quals)
        .map(|(r, q)| {
            let fallback = vec![b'I'; r.len()];
            Prep {
                km: kcodes(r, A),
                lq: lowq(if q.len() == r.len() { q } else { &fallback }),
            }
        })
        .collect()
}

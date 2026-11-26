use super::calls::locate;
use super::{FlankIndex, Prep};

fn merge(a: &[(usize, u8)], b: &[(usize, u8)]) -> Vec<(usize, u8)> {
    let mut out = Vec::with_capacity(a.len() + b.len());
    let (mut i, mut j) = (0, 0);
    while i < a.len() && j < b.len() {
        if a[i].0 < b[j].0 {
            out.push(a[i]);
            i += 1;
        } else if b[j].0 < a[i].0 {
            out.push(b[j]);
            j += 1;
        } else {
            let base = if a[i].1 == b[j].1 { a[i].1 } else { b'N' };
            out.push((a[i].0, base));
            i += 1;
            j += 1;
        }
    }
    out.extend_from_slice(&a[i..]);
    out.extend_from_slice(&b[j..]);
    out.retain(|x| x.1 != b'N');
    out
}

pub(super) fn pair_calls(
    pr: [&Vec<u8>; 4],
    pp: [&Prep; 4],
    index: &FlankIndex,
) -> Vec<(usize, u8)> {
    let o = [
        locate(pr[0], pp[0], index),
        locate(pr[1], pp[1], index),
        locate(pr[2], pp[2], index),
        locate(pr[3], pp[3], index),
    ];
    let (a, b) = match &o {
        [Some(r1), None, None, Some(r2)] if r1.st <= r2.st => (r1, r2),
        [None, Some(r1), Some(r2), None] if r2.st <= r1.st => (r1, r2),
        _ => return Vec::new(),
    };
    let longest = pr.iter().map(|r| r.len()).max().unwrap_or(0);
    if (a.en.max(b.en) - a.st.min(b.st)) as usize
        > longest.saturating_mul(2).saturating_add(200).min(750)
    {
        return Vec::new();
    }
    merge(&a.pairs, &b.pairs)
}

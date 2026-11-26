use super::evidence::Prep;
use super::scan::{observations, unsupported_pair};

pub(super) fn incompatible(seq: &[u8], reads: &[Vec<u8>], preps: &[Prep], sigs: &[u32]) -> bool {
    let calls = observations(seq, reads, preps);
    let mut counts = vec![[0usize; 4]; seq.len() + 1];
    for group in &calls {
        for &(pos, b) in group {
            let i = match b {
                b'A' => 0,
                b'C' => 1,
                b'G' => 2,
                b'T' => 3,
                _ => continue,
            };
            if pos < counts.len() {
                counts[pos][i] += 1;
            }
        }
    }
    let mut var = Vec::new();
    for (pos, c) in counts.iter().enumerate() {
        let Some(ri) = b"ACGT"
            .iter()
            .position(|&b| b == seq.get(pos).copied().unwrap_or(b'N'))
        else {
            continue;
        };
        if c[ri] >= 5 && c.iter().sum::<usize>() - c[ri] >= 5 {
            var.push(pos);
        }
    }
    let longest = reads.iter().map(Vec::len).max().unwrap_or(0);
    let max_span = longest.saturating_mul(2).saturating_add(200).min(750);
    unsupported_pair(seq, &calls, sigs, &var, max_span)
}

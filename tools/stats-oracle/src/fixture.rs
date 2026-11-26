//! Deterministic, reference-blind control fixture: 6 x 8000 bp contigs and
//! 80,000 x 250 bp original pairs. No truth, reference, score or environment
//! input. The exact generator is part of the published artifact contract.
pub struct Rng(u64);

impl Rng {
    pub fn new(seed: u64) -> Self {
        Self(seed)
    }
    pub fn next(&mut self) -> u64 {
        self.0 = self
            .0
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        self.0 >> 32
    }
}

fn complement(base: u8) -> u8 {
    match base {
        b'A' => b'T',
        b'T' => b'A',
        b'C' => b'G',
        _ => b'C',
    }
}

fn reverse_complement(read: &[u8]) -> Vec<u8> {
    read.iter().rev().map(|&b| complement(b)).collect()
}

/// The two documented fixture generators. `lcg` is the default.
pub fn build(mode: &str) -> (Vec<Vec<u8>>, Vec<Vec<u8>>) {
    let mut rng = Rng::new(0x2026_1126_5354_4f52);
    let mut contigs = Vec::new();
    for c in 0..6 {
        let seq: Vec<u8> = (0..8000)
            .map(|j| match mode {
                "cycle" => b"ACGT"[(j + c) % 4],
                _ => b"ACGT"[(rng.next() % 4) as usize],
            })
            .collect();
        contigs.push(seq);
    }
    let mut seqs = Vec::with_capacity(80_000 * 4);
    for _ in 0..80_000 {
        let c = (rng.next() % 6) as usize;
        let start = (rng.next() as usize) % (8000 - 250 - 1);
        let first = contigs[c][start..start + 250].to_vec();
        let second = contigs[c][start + 1..start + 251].to_vec();
        for read in [first, second] {
            seqs.push(read.clone());
            seqs.push(reverse_complement(&read));
        }
    }
    (contigs, seqs)
}

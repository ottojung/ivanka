/// Reusable per-pair locus accumulator for at most sixteen candidates.
/// Generation tags deduplicate loci in O(1) without clearing between pairs;
/// locus vectors retain capacity across the whole scan.
pub(super) struct Accumulator {
    seen: Vec<Vec<u32>>,
    loci: Vec<Vec<usize>>,
    generation: u32,
    touched: u16,
}

impl Accumulator {
    pub(super) fn new(lengths: &[usize]) -> Self {
        Self {
            seen: lengths.iter().map(|&n| vec![0; n]).collect(),
            loci: (0..lengths.len()).map(|_| Vec::new()).collect(),
            generation: 0,
            touched: 0,
        }
    }

    pub(super) fn begin(&mut self) {
        self.generation += 1;
        self.touched = 0;
    }

    pub(super) fn insert(&mut self, candidate: usize, locus: usize) {
        let mark = &mut self.seen[candidate][locus];
        if *mark != self.generation {
            *mark = self.generation;
            self.loci[candidate].push(locus);
            self.touched |= 1 << candidate;
        }
    }

    pub(super) fn apply(&mut self, mut visit: impl FnMut(usize, &[usize])) {
        let mut bits = self.touched;
        while bits != 0 {
            let candidate = bits.trailing_zeros() as usize;
            bits &= bits - 1;
            visit(candidate, &self.loci[candidate]);
            self.loci[candidate].clear();
        }
    }
}

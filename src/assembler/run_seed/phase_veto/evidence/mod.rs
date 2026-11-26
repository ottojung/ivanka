mod encode;
mod quals;
mod sign;

use std::collections::HashMap;
use std::hash::{BuildHasherDefault, Hasher};

pub(super) use encode::{validw, A, INV, K128};
pub(super) use quals::make_preps;
pub(super) use sign::{signature_ids, uniq_flanks};

const Q15: u8 = 48;

pub(super) struct Prep {
    pub km: Vec<u64>,
    pub lq: Vec<usize>,
}

#[derive(Default)]
pub(super) struct FastHasher(u64);

impl Hasher for FastHasher {
    fn write(&mut self, b: &[u8]) {
        for &x in b {
            self.0 = self.0.rotate_left(5) ^ (x as u64);
        }
    }

    fn write_u128(&mut self, i: u128) {
        self.0 = (i as u64).wrapping_mul(0x9E3779B97F4A7C15)
            ^ ((i >> 64) as u64).wrapping_mul(0xC2B2AE3D27D4EB4F);
    }

    fn finish(&self) -> u64 {
        let mut x = self.0;
        x ^= x >> 30;
        x = x.wrapping_mul(0xBF58476D1CE4E5B9);
        x ^= x >> 27;
        x
    }
}

pub(super) type FlankIndex = HashMap<K128, Option<usize>, BuildHasherDefault<FastHasher>>;

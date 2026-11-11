// Experimental search budgets; defaults reproduce native Ivanka.

use std::env;

fn validate(value: Option<&str>, default: usize) -> usize {
    let Some(raw) = value else {
        return default;
    };
    let parsed = raw
        .parse::<usize>()
        .expect("invalid experimental seed limit");
    assert!(
        parsed >= 1 && parsed <= default,
        "out-of-range experimental seed limit"
    );
    parsed
}

pub(super) fn limits() -> (usize, usize) {
    let primary = env::var("IVANKA_BENCH_PRIMARY_SEEDS").ok();
    let rescue = env::var("IVANKA_BENCH_RESCUE_SEEDS").ok();
    let limits = (
        validate(primary.as_deref(), 1000),
        validate(rescue.as_deref(), 400),
    );
    eprintln!(
        "IVANKA_SEED_BUDGET primary={} rescue={}",
        limits.0, limits.1
    );
    limits
}

#[cfg(test)]
mod tests;

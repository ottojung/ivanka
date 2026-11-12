// Default search bounds are sufficient for the read-backed MiCall workflow.
// Optional overrides are diagnostic controls, never required for normal use.

use std::env;

fn validate(raw: Option<&str>, default: usize, name: &str) -> Result<usize, String> {
    let Some(raw) = raw else { return Ok(default) };
    let value = raw
        .parse::<usize>()
        .map_err(|_| format!("{name} must be an integer from 1 to {default}"))?;
    if !(1..=default).contains(&value) {
        return Err(format!("{name} must be from 1 to {default}"));
    }
    Ok(value)
}

pub(super) fn limits() -> Result<(usize, usize), String> {
    let primary = env::var("IVANKA_BENCH_PRIMARY_SEEDS").ok();
    let rescue = env::var("IVANKA_BENCH_RESCUE_SEEDS").ok();
    let limits = (
        validate(primary.as_deref(), 50, "IVANKA_BENCH_PRIMARY_SEEDS")?,
        validate(rescue.as_deref(), 20, "IVANKA_BENCH_RESCUE_SEEDS")?,
    );
    eprintln!(
        "IVANKA_SEED_BUDGET primary={} rescue={}",
        limits.0, limits.1
    );
    Ok(limits)
}

#[cfg(test)]
mod tests;

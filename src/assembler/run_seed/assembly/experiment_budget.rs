//! Stable search budgets are part of the assembler's Rust defaults.

/// MiCall and standalone Ivanka receive identical limits with no tuning.
pub(super) fn limits() -> Result<(usize, usize), String> {
    let limits = (50, 20);
    eprintln!(
        "IVANKA_SEED_BUDGET primary={} rescue={}",
        limits.0, limits.1
    );
    Ok(limits)
}

#[cfg(test)]
mod tests;

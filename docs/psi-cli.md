# PSI command-line calculator

Run from the Ivanka repository root:

```sh
printf '1 1 -2\n' | python3 benchmarks/psi.py
printf '1, 1, -2\n' | python3 benchmarks/psi.py --json
```

Human-readable output uses Unicode mathematical symbols (e.g. Ψ, ∞, −∞ and ℝ).
For example:

\`\`\`text
Ψ(0) = 0.3333333333
Ψ(1) = 0.3333333333
Ψ(2) = −0.3333333333
Ψ(+∞) = −∞
{ r : Ψ(r) = 0 } = { 1.709511291 }
\`\`\`

The \`--json\` mode deliberately remains ASCII-only, using \`"-inf"\` and \`"+inf"\`.

Input is one or more finite signed numbers `p_i`, separated by whitespace or
commas, with optional `#` comments. Zero differences contribute zero and are
included in the denominator `n`. Blank input, NaN and infinities are rejected.

This CLI implements **shifted signed powers**:

```text
Psi(r) = (sum(sign(p_i) * (1 + abs(p_i)) ** r)) / n
```

It prints `Psi(0)`, `Psi(1)`, `Psi(2)`, the extended-real limit at positive
infinity, and **every finite real zero** of `Psi(r)` (including negative `r`).
Zeros are isolated recursively: divide an exponential sum by its lowest
exponential, differentiate to reduce its number of terms by one, and bisect
on the resulting monotone intervals. Tangential zeros are detected at
stationary points. Equal magnitudes are grouped exactly before taking logs.

The zero set includes only finite real roots, excluding infinite limits.
When it is empty, human-readable output uses ∅ and JSON uses [].
The positive-infinity limit is reported separately; JSON encodes it as
the strings +inf, -inf, or 0, never a nonstandard numeric constant.
If `Psi` is identically zero, `zeros` becomes `"R"`.

`--digits` (default 10) sets reported significant figures; `--precision`
(default 65) sets Decimal working precision. The root positions are numerical
approximations, **not formally certified isolating intervals**. Extremely
close roots or nearly tangential extrema may require increasing `--precision`.
No non-standard Python packages are required.

When PSI is identically zero, human output uses ℝ and ASCII JSON uses "R".

JSON output is tab-indented for readability and is ASCII-only.

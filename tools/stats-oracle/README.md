# Packed stats-dump provenance oracle (test only)

Standalone, dependency-free harness that closes the **documentation** half of
the provenance gap disclosed in the 2026-11-25 `[independent-review-pr466-rebased]`
board comment. It vendors, byte-for-byte, the index/scoring modules of the
reviewed exact head `732b64ca1cd77cc4e230e0724673297bfe652b10` (PR #466) and the
byte-key baseline head `47ee44c22d26f0e2991526493cc8e42e669a6d9c` (PR #463),
then recomputes the full packed/byte statistics dumps over one deterministic,
reference-blind fixture. No production Ivanka source, threshold, benchmark
data, frozen artifact, MiCall output or image is changed or read by this tool.

## Exact command

```sh
cd tools/stats-oracle
CARGO_TARGET_DIR=/tmp/<your-own-dir>/target cargo run --release --quiet -- \
  --fixture lcg --vendor-hashes --out /tmp/<your-own-dir>/evidence
```

Optional flags: `--fixture cycle` (alternate documented generator),
`--order 0,1,2,3` (field order; default depth,pairs,coverage,masks),
`--endian le|be`, `--scan-framings` (all 24 orders x both endiannesses),
`--verify-file <path>` (hash an already-preserved dump and compare it to the
published literal). All hashes are computed with an in-tree SHA-256 and were
cross-checked against `sha256sum`.

## Exact inputs

- Vendored sources: the seven `src/assembler/run/read_backed/{index,scoring}`
  files of `732b64ca` and the six of `47ee44c2`; every file's SHA-256 is printed
  by `--vendor-hashes`. The only added files in those two trees are empty
  `scoring/tests.rs` shims, present solely so rustfmt can resolve the vendored
  `#[cfg(test)] mod tests;` declarations; they contain no logic. The two
  pipelines are asserted byte-equal field by field before any digest is emitted.
- Fixture `lcg`: one 64-bit LCG (`state = state*6364136223846793005 +
  1442695040888963407`, output `state >> 32`, seed `0x2026_1126_5354_4f52`)
  generates six 8,000 bp contigs over `ACGT` and 80,000 read pairs of 250 bp
  sampled from those contigs; `seqs` is `[R1, RC(R1), R2, RC(R2)]` per pair, as
  in `reads/load/pairs.rs`. No reference, truth, score or environment input.
- Serialization: depths as `u32`, pairs and coverage as `u64`, masks as `u16`,
  little-endian, in field order depth, pairs, coverage, masks. With 47,820
  depth loci and 80,000 masks this is exactly **351,376 bytes**; the harness
  asserts that length.

## Published literals and verdict

| artifact | published literal | this harness (fixture `lcg`) | reproduced |
| --- | --- | --- | --- |
| packed stats dump | `f45f93afa3484e7b3a9f790b9f915b91a5d13ed09967c5446ccf7cf476d6c269` | `9eefadf80c4fbfef3cabe4e6abc9a8f268589e080ba4e9f39ae08e85aae5b265` | NO |
| assembled FASTA | `f6cc54774995558c7dd8fa27713937e36aa1aa16dc9b62a767d8e73a8d965f3e` | `38bbee4e120722c2b4c8537e542469a3b47a7ee65f0b45f0a500b9cb35d47ef2` | NO |

**Typed verdict: NOT BYTE-REPRODUCIBLE.** The published literals belong to the
original owner's uncommitted harness (`/tmp/opencode/perf-baseline-stats.txt`,
`/tmp/opencode/perf-opt-stats.txt`, and its `#[cfg(test)]` generator), all since
removed from this host. Neither the byte framing nor the deterministic fixture
generator was committed, and the original review independently obtained
`7388d616ac3b4c3d4ab712ca90a29f4f2aa90d0086b62f5ec5d6d91130d05855` over a
different 351,376-byte reconstruction. The 24 field orders x 2 endiannesses
and both documented fixture generators were scanned; none yields either
published literal. This harness therefore makes the *framing* explicit and
reproducible, and provides `--verify-file` to authenticate any recovered
original dump, but it does **not** recover the missing original bytes. The
byte-equivalence conclusion itself is independently re-verified: packed and
byte-key pipelines produce identical fields and identical dumps here.

Closest reproducible artifacts in this checkout: the `lcg` dump above, plus
the `cycle` fixture dump `c4840c2061b62d24fd39b95a6ea815eb06769ccbb82276158ecb8274a6d6e462`
and FASTA `340f945c9972bba9c60af4a8ebffc400e580513600148221b0d7a22c62f43f19`.
Neither is a substitute for the published literals; no claim of provenance
recovery is made.

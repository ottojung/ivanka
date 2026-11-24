# Lossless storage for retained scientific tables

Founder authorization (2026-11-24 06:01 UTC) covers lossless compression of
retained scientific results and later migration of existing data. This
document specifies the storage contract only. Producing, publishing or
re-scoring benchmark measurements is out of scope, and no MiCall source or
container is changed.

## Logical names and proof sidecar

A retained CSV keeps its logical name (for example `genome_coverage.csv`).
It is stored either as the original plain bytes or as:

* `genome_coverage.csv.zst` — one zstd frame; and
* `genome_coverage.csv.zst.meta.json` — the proof sidecar.

The proof records `format` (`ivanka-zstd-table/1`), `codec` (`zstd`),
`level` (3), `threads` (1), `checksum` (true), `original_name`,
`original_sha256`/`original_size` of the **uncompressed bytes**, and
`compressed_sha256`/`compressed_size` of the stored frame. Digests are
SHA-256. Content provenance that pins plain-byte digests therefore stays
valid: readers always report the digest and size of the uncompressed table.

## Reproducible frame contract

Exactly one zstd frame, compression level 3, one worker, frame checksum
enabled, no pledged content size. The portable implementation is the
`backports.zstd` package (PEP 784 API) declared in
`benchmarks/requirements.txt`. The fallback is a zstd 1.5.x CLI invoked with
`-3 -T1 --check`; select it with `IVANKA_ZSTD_BACKEND=cli` and optionally
`IVANKA_ZSTD_PATH`. Readers depend only on the zstd frame contract and the
checksum, not on a particular encoder's byte layout.

## Reader and writer rules

`benchmarks/compressed_tables.py` is the single owner of this file I/O:

* `find_table` / `open_table` give callers one logical table regardless of
  storage; `logical_digest` returns the uncompressed SHA-256 and size.
* A plain and compressed variant may coexist only when both prove the same
  uncompressed digest and size. Conflicting variants, an unknown codec, a
  missing or invalid proof, a changed compressed payload and a truncated
  frame all fail closed.
* `compress_table` streams in bounded 64 KiB chunks, writes to unique
  temporary files, verifies the compressed proof and a full decompressed
  SHA-256/size readback, then atomically installs frame and proof before
  removing the plain file. Re-running a completed or interrupted attempt is
  idempotent and never rewrites a proven pair.
* Only entries in `COMPRESSIBLE_TABLES` (large diagnostic tables) may be
  compressed. Final consensus, contig and receipt-sized tables stay plain
  because immutable external consumers open those paths directly.

## Integration and sequencing

The transparent readers are wired into diagnostic metrics, project reference
selection, exact sidecar generation/verification, archived publication and
checkpoint provenance consumers. No existing table has been migrated by this
change: migration is a separate agent's responsibility and must not begin
until every relevant reader has shipped. Source pins in
`benchmarks/assembler_bench/px_source_pins.py` were recomputed for the two
intentionally modified reader files; scoring formulas, thresholds and
original terminal receipts are unchanged.

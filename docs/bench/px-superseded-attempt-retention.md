# Superseded PX attempt retention

A transient infrastructure failure can leave a large scratch directory even
when the bounded retry later resolves the case. The archive is not the
canonical measurement. Its receipt, launcher log, native assemblies, final
scientific files and diagnostics remain evidence. The retention module touches
only explicitly recognized, regenerable reads, mappings and indices, not whole
scratch trees or unknown native artifacts.

The default storage mode archives each eligible file at its original logical
path: `temp.sam.zst` plus `temp.sam.zst.meta.json`. The proof records the
SHA-256 and size of the **uncompressed** bytes, so retry, score and sealed
receipt provenance keep their plain-byte digests. Readers that need the bytes
ask for the logical path and consume verified, decompressed chunks; a restore
recreates byte-identical plain files at those paths and removes the frames.

The supervisor archives after recording a resolved retry and checkpoint. The
operator can also inspect, archive or restore older archives:

```sh
PYTHONPATH=.:benchmarks python3 -m benchmarks.assembler_bench.px_attempt_retention \
  --root "$PX_ROOT"
# Only at a quiescent worker boundary (the command refuses a busy lock):
PYTHONPATH=.:benchmarks python3 -m benchmarks.assembler_bench.px_attempt_retention \
  --root "$PX_ROOT" --apply
PYTHONPATH=.:benchmarks python3 -m benchmarks.assembler_bench.px_attempt_retention \
  --root "$PX_ROOT" --restore
```

Use `--only <exact archive name>` to limit the action. A dry run reports
eligible allocated bytes based on receipt and historical teardown proof; it
does not claim current container absence or perform any mutation. Apply must
acquire the actual global worker lock and observe absence of the exact CID in
the pinned PX store. It requires the indexed canonical second terminal receipt,
a matching second attempt copy, the original classified infrastructure failure,
a unique matching launcher log hash, matching report and released worker lease.
A successful superseding receipt also requires its preserved final MAX digest.
Unresolved infrastructure failures, orphan archives, missing/ambiguous evidence,
unsafe paths, and multiply linked files are refused. Restore requires the same
binding, global worker lock, fresh exact CID absence and workspace headroom.
Compression is refused when the proven frame and proof do not reduce the file's
apparent size.

On apply the module seals the original failure, source digests and every
candidate's logical digest and size before any file changes. Every source is
reverified immediately before compression or deletion; each frame is verified
by compressed digest and full decompressed readback before it replaces the
plain file. Workspace headroom is preflighted from the source size plus a
bounded codec expansion allowance, then rechecked with the measured frame
size, so the shared reserve is not breached while a temporary frame is built.
An interrupted operation resumes from the same seal: a plain file that
reappears is re-verified, and a complete pair with no plain file is accepted
only when both variants prove the sealed digest. A crash between publishing
the frame and its proof is repaired only while the plain source remains; a
partial pair without its source fails closed for operator recovery. A changed
proof, symlinked or multiply linked variant, or a missing source is refused.
Receipts, results, logs, native outputs and every other scientific file are
never rewritten or removed. Cleanup failures do not invalidate terminal
science.

Delete mode (`--mode delete`) is an explicit operator action for cases where
no reversible frame is wanted. It uses the same binding, seal and revalidation
rules, but unlinks the verified sources without retaining their bytes.

```sh
PYTHONPATH=.:benchmarks python3 -m benchmarks.assembler_bench.px_attempt_retention \
  --root "$PX_ROOT" --apply --mode delete
```

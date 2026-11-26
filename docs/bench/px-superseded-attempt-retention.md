# Superseded PX attempt retention

A transient infrastructure failure can leave a large scratch directory even
when the bounded retry later resolves the case. The archive is not the
canonical measurement. Its receipt, launcher log, native assemblies, final
scientific files and diagnostics remain evidence. The retirement module removes
only explicitly recognized, regenerable reads, mappings and indices, not whole
scratch trees or unknown native artifacts.

The supervisor calls retention after recording a resolved retry and checkpoint.
The operator can also inspect or retire older archives:

```sh
PYTHONPATH=.:benchmarks python3 -m benchmarks.assembler_bench.px_attempt_retention \
  --root "$PX_ROOT"
# Only at a quiescent worker boundary (the command refuses a busy lock):
PYTHONPATH=.:benchmarks python3 -m benchmarks.assembler_bench.px_attempt_retention \
  --root "$PX_ROOT" --apply
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
unsafe paths, and multiply linked files are refused. On apply the module seals
the original failure, source digests and every proposed deletion's digest and
size before unlinking; a partially completed operation is replayable from the
same seal. Receipts, results, log files and unknown native outputs are never
rewritten or removed. Cleanup failures do not invalidate terminal science.

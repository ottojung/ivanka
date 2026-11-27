# Strict paired-anchor spanning of large unobserved truth-window runs

Posthoc only. This follows the observed-island analysis, using the same 32 synthetic single-truth cases and exact source pins. It asks whether an original read pair has consistent unique 31-mer anchors on opposite sides of an unsupported run of at least 150 consecutive truth-window start positions.

The reader verifies paired FASTQ record IDs and mate labels. Each mate must contain at least two non-overlapping, individually unique exact anchors that agree on its ungapped placement and orientation. The placements must face inward and have the left mate's last anchor start before the gap and the right mate's first anchor start at or after its end. Repeats, conflicting placements and unsupported mates are excluded, not treated as evidence. Counts are record counts and distinct ordered read-string-pair counts, not molecule counts.

| Family | Cases | Large absent window runs | Read pairs | Both mates anchored | Runs spanned by at least one accepted pair |
|---|---:|---:|---:|---:|---:|
| PCR jackpot | 16 | 145 | 160,000 | 159,966 | 0 |
| Coverage hole | 16 | 16 | 160,000 | 159,964 | 0 |

These observations make forced continuity across these large intervals a poor immediate direction. This is **not** a proof of absence of all linkage, or an upper bound on alignment or score. The anchor test excludes indel-displaced, ambiguous and conflicting anchors; it does not evaluate other graph evidence or reconstruct intervening bases. No reference or truth is supplied to the assembler. No qualification criterion changes.

The first run stopped after 30 cases at the cgroup headroom gate. Its 30 complete records remain sealed on the host. After headroom recovered, a fresh bounded run completed all 32 and exited 0; the second raw JSONL SHA-256 is `0fca43a83ecd3cd582e899fca25c6b80ad40ebd76c8518559d0a6a9074d2b66c`. The committed report is a derived JSON representation with the validated case order, record hashes checked before conversion, and explicit completed count. No raw reads or sequences are published.

Reproduce on the retained input host (33 GiB disk reserve, 1 GiB cgroup headroom, 256 MiB process AS limit, 240 s deadline):

```sh
PYTHONPATH=.:benchmarks python3 benchmarks/p1_pair_spanning.py \
  --posthoc docs/bench/diagnostics/p1-adapter-mode-posthoc-complete-20261126.json \
  --data "$SYNTHETIC_DATA_ROOT" \
  --output-root "$NATIVE_AUDIT_RUNS_ROOT" \
  --output /tmp/p1-pair-spanning.jsonl
```

Use a unique output path; an incomplete JSONL prefix is not a complete report. No build or assembly occurs.

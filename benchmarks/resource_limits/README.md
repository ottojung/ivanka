# External 40-minute / 4-GB policy

This outer Podman proxy is independent of the frozen MiCall images and clinical
source. It rewrites only ivanka-bench-* container create/run actions: --timeout
is capped at 2398 seconds, and --memory and --memory-swap are capped at
4,000,000,000 bytes. The 2400-second overall budget must also be verified
from recorded wall time. All other Podman operations are transparently passed.

The proxy writes a per-invocation audit record with container identity,
effective limits and immutable image hash, but never edits an old JSONL result.
Historical uncapped successes do not prove that they ran with a 4-GB cgroup cap.
Existing old 50-minute outcomes must be kept and classified separately.

# External synthetic worker fallback

This module adjusts only outer benchmark runner concurrency. The clinical
MiCall source, seven frozen container images, existing synthetic score records
and the source-attested six-comparator controller stay immutable.

Choose three workers only if cgroup raw headroom >=8 GiB and reclaimable
headroom >=12 GiB. Otherwise use two workers if reclaimable headroom >=8 GiB.
Below that level fail closed rather than risk cgroup OOM. The underlying stage
still has its original 5-GiB/8-GiB admission guard on every third-worker enqueue.
If its guard trips mid-run, the external service permanently downgrades to two
workers within that service process, rather than retrying three indefinitely.
Every resumed arm reuses the same source-attested completed output. Never
interpret the file cache as an actual per-container kernel memory limit.

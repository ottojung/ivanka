# 40-minute / 4-GB external resource policy

The frozen MiCall images and all historical checkpoints stay unchanged.
New attempts use an external benchmark-only Podman adapter: request
`--timeout=2398`, `--memory=4000000000`, and
`--memory-swap=4000000000`. The independent 100-ms RSS guard currently
terminates MiCall trees after observing 3,700,000,000 resident bytes.

**Important limitation:** this host mounts the shared cgroup controller
read-only and does not delegate a separate memory cgroup to containers.
Podman's requested 4-GB memory cap is visible in HostConfig, but its memory
cgroup is not applied. The RSS guard is best-effort, not an exact kernel limit;
an allocation can jump past 4 GB before a 100-ms sample. Do not claim hard-cap
qualification until a verified delegated memory cgroup exists.

Historical source-attested successes remain valid observations. Do **not**
silently reclassify a 50-minute success as passing the 40-minute policy, nor
claim an uncapped attempt proves 4-GB compliance. No successful old attempts
are automatically repeated. Original failed 30-minute attempts can be eligible
for one bounded 40-minute retry; already terminal 50-minute attempts stay
terminal, whether they failed or succeeded.

The read-only qualification scanner writes a separate derived summary and
never touches results.jsonl, checkpoints, artifacts, or OCI layers.
Its categories explicitly distinguish: failed, >40m, sampled >4 GB, missing
RSS, legacy uncapped, and newly capped-but-not-kernel-proven.
Use the versioned report as an operational qualifier, not a new clinical score.

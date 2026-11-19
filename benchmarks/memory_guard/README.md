# Fail-closed conservative memory guard

Podman reports --memory=4000000000 on marceline-dev but the running
containers share the host-level read-only cgroup (30 GiB). The OCI setting
alone does not enforce an isolated 4-GB limit. This independent watchdog
samples all benchmark MiCall processes and descendants every 100 ms and
terminates a tree at 3.7 GB summed VmRSS; the 300 MB safety margin reduces
but cannot mathematically rule out transient >4 GB allocations. The
resulting MiCall exit remains a real terminal FAILURE, never a success.
Each kill is written to a durable append-only audit. The frozen MiCall
source/images and existing result checkpoints are unchanged. For rigorous
kernel-level hard isolation, the operator must provide writable/delegated
memory cgroups or a suitable host.

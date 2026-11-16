# Future comparator retry: preserve running MiCall under ambiguous wait

This is an **experimental, not yet deployed** Podman lifecycle change.
The source-pinned six-comparator original physical198 and synthetic400
jobs retain their original runner code, immutable OCI image IDs, per-arm
1800-second budget, acceptance rules and event journals. Do not cherry-pick
this change into a currently executing source-attested run.

Podman's documented `wait` command may emit `-1`, rather than an
authentic process exit code, when a different condition is observed.
The current physical comparator source sometimes sees `-1` from the
exact immutable created ID, and has already recorded failure evidence.
We **do not** know why each of those containers returned `-1`; an
unverified failed arm is not proof of biological assembly inferiority.

The experimental lifecycle runs the original Podman `create`, `start`,
`wait`, `logs` and `rm` sequence under the same 1800-second
wall-clock budget. No new MiCall command, source reads, references or
assembler parameters are introduced. If three invalid `wait` responses
are observed, it performs read-only `podman inspect` on the **same exact
created container ID** under the original metadata lock.

* A genuinely exited container, with a trusted integral 0–255 exit
  code, non-default start time, `Running=false`, `OOMKilled=false`,
  and `Dead=false`, may supply its immutable exit code.
* If **exactly that ID** is proven `Status=running`, `Running=true`,
  `OOMKilled=false`, `Dead=false`, and it has a non-default start
  time, the helper retains the container and continues waiting,
  without creating or restarting MiCall. This path never claims success
  until a subsequent authenticated exit and full logs/removal.
* Missing, malformed, inconsistent, dead, killed, absent or stale
  container state fails closed. Persistent `-1` after the original
  sample deadline remains failure/timeout, never an invented success.
* If a genuine terminal nonzero exit can be authenticated, it remains
  nonzero; failed attempts cannot be converted into score advantages.

The new hermetic lifecycle test reproduces three `-1` responses while
a single exact-ID container is still running, then a subsequently
verifiable zero exit; it proves just one start, four `wait` calls,
one read-only inspect, one regular removal, and no forced termination.
Original tests continue to reject forged terminal states and incomplete
or killed containers.

This source should only be considered for an **independent,
source-pinned follow-up diagnostic attempt of previously unverified
infrastructure failures**, after completing all first-pass fixed
comparator cohorts. Original attempts and their failures must remain
immutable; a follow-up cannot retroactively change their results or
pass release acceptance criteria.

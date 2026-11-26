# P1 watchdog s6 deployment + readiness probe — exact source-only plan (2026-11-26)

**Status: SOURCE-ONLY. The watchdog is NOT deployed or armed by this change.**
Deployment and arming are an explicit operator action at a natural PX boundary.
This document and `benchmarks/expanded/p1_watchdog_readiness.py` only read the
host; they never install a service, write an ALIVE record, take the PX lock,
write a lease/STOP, invoke Podman, or touch a live arm.

## 1. Actual s6 layout (read-only verified on host marceline-dev)

| Item | Verified value |
|---|---|
| s6 scan dir | `/run/service` (s6-svscan pid 1, `-d4 -- /run/service`) |
| service dirs | `/run/s6/legacy-services/<name>` |
| activation | `/run/service/<name>` is a symlink to `/run/s6/legacy-services/<name>` |
| run file | `<service dir>/run`, executable, exports pins **inline** (no `env/` dir on this host) |
| supervisor | `<service dir>/supervise/status` |
| existing PX service | `px-cohort-supervisor` → `/run/s6/legacy-services/px-cohort-supervisor`, **up** (live PX arm) |
| retired legacy P1 service | `ivanka-p1-narrow-canary` (inert; source-pinned image absent; do not restart) |
| watchdog service | **absent** — `/run/service/ivanka-watchdog` does not exist; `WATCHDOG_ARMED` not set |

The independent watchdog's run script is source-only at
`scripts/px_watchdog_s6_service.sh` on exact PR527 `b185c7f2`. It discovers
active leases from the shared durable journal, never holds the PX worker lock,
writes only an append-only evidence journal, and requires `WATCHDOG_ARMED=1`
plus complete pins before doing anything.

## 2. Exact pins the deployed service must satisfy (fail closed)

| Export / artifact | Required value | Source |
|---|---|---|
| `WATCHDOG_ROOT` | `/workspace/ivanka-exploratory-ten-20261121` | actual PX worker root; hosts `.worker-lease.jsonl` and `.watchdog-alive.json` |
| `WATCHDOG_CODE` | a reviewed PR527 checkout whose `benchmarks/fail_closed_guard/watchdog_cli.py` SHA256 is `e00b83adfbf8356f2f92ce92ecd2226854a182d21a21e24ca87d35ed205b5369` | exact reviewed head `b185c7f2b95c84edce5f1323f93addd5be7ead2d` |
| `WATCHDOG_STORAGE_CONF` | `/workspace/ivanka-exploratory-ten-20261121/storage.conf` (SHA `fdf5ce294ebcd8a950d1ae2016032a2620e9b16cabf33c772dc43ab425ecec21`) | shared PX store |
| `WATCHDOG_GRAPHROOT` | `/workspace/ivanka-exploratory-podman-20261121/store` | derived from the shared PX storage.conf |
| `WATCHDOG_ARMED` | `0` until operator authorization at a natural PX boundary; `1` only after | operator gate |
| module | `python3 -m fail_closed_guard.watchdog_cli` | watchdog service script |
| ALIVE record | `WATCHDOG_ROOT/.watchdog-alive.json`, schema `ivanka.watchdog-alive.v1`, fresh (`<=30s`), identity-bound (live pid/starttime/pid_ns), graphroot bound | `watchdog_contract.require_watchdog_readiness` |

## 3. Exact probe (safe to run now; read-only)

```sh
cd /workspace/ivanka-p1-pilot-950fe331-20261126
PYTHONPATH=.:benchmarks python3 -m expanded.p1_watchdog_readiness --check
# rc=0 only when the s6 service is present, executable, pinned, armed AND the
# shared ALIVE record is fresh/identity-bound/graphroot-bound; rc=1 otherwise.

PYTHONPATH=.:benchmarks python3 -m expanded.p1_watchdog_readiness --deployment-plan
# prints the exact source-only deployment plan (no execution)
```

Current real-host result (17:52Z window): **not ready, fail closed** —
`s6 activation symlink missing`, `WATCHDOG_ARMED` absent, and
`watchdog_alive.reason = watchdog_unavailable`. This is expected: the watchdog
is deliberately not deployed. No arm is attempted.

Tests: `PYTHONPATH=.:benchmarks python3 -m pytest -q benchmarks/test_p1_watchdog_readiness.py`
(12 deterministic tests over a simulated s6 layout; no live service touched).

## 4. Operator deployment sequence (NOT performed here)

1. At a natural PX boundary, with the operator holding the shared
   `/workspace/ivanka-exploratory-ten-20261121/.global-worker.lock` window,
   create the service dir `/run/s6/legacy-services/ivanka-watchdog` with an
   executable `run` that exports exactly the pins in section 2 and execs the
   pinned `fail_closed_guard.watchdog_cli` with `--root`, `--storage-conf` and
   `--graphroot` set to those values. Keep `WATCHDOG_ARMED=0` initially.
2. Activate with `ln -s /run/s6/legacy-services/ivanka-watchdog /run/service/ivanka-watchdog`.
   s6-svscan picks it up; the service idles while unarmed.
3. Run the probe from section 3. It must report the layout/pins ready before
   any arming; if the ALIVE record is absent the probe stays not-ready and no
   slot may be granted.
4. Only after the operator explicitly authorizes at the natural PX boundary:
   set `WATCHDOG_ARMED=1`, confirm a fresh identity-bound ALIVE record naming
   the PX graphroot, and re-run the probe until `ready=true`.
5. Then (and only then) write `operator-slot.json` with an exact non-expired
   token and run the pilot `--check` followed by `--armed --slot`.

The watchdog never holds the PX global worker lock; the pilot's exclusion is
proven by `verify_shared_px_boundary()` against the same lock, journal and
graphroot. No `pilot.lock` or private lease root is acceptable.

## 5. Real-host absence-format evidence (operator 17:52Z)

Podman 5.8.2, isolated read-only-image namespace, no live container or
benchmark touched:
- `podman inspect --format ... <absent-full-CID>` → rc125, stderr exactly
  `Error: no such object: "<full CID>"`.
- `podman container inspect ... <absent-full-CID>` → rc125,
  `no such container "<full CID>"`.
Both match the strict optional-colon full-CID matcher at reviewed PR527 head
`b185c7f2` (`binding.absent_evidence` now matches stderr only, never argv/
`str(exc)`). Do not weaken this matcher; a bare no-CID diagnostic fails closed.

## 6. Boundaries

No arm, deploy, install, image build/import, container, STOP/lease write, PX
pause, case run, frozen-evidence change, receipt/threshold/scoring/seal
mutation, seven-way/P1 qualification or clinical claim. Issue stays OPEN;
`STATUS=ATTEMPTED_NOT_QUALIFIED`, `kernel_enforcement=false`.

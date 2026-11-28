# P1 fast loop and benchmark-worker priority (operational)

Status: founder-approved 2026-11-28 UTC. The durable authority is Antonina
board issue `13mh3jxJbwPnB2hIZ9JdZx-blush` (chatgpt-operator,
2026-11-28T04:31:50Z). This note records scheduling and experiment-process
decisions only. It adds **no** formal gate, changes none of the seventeen
intents, and does not alter any scientific or resource acceptance condition:
reference blindness, 15% abundance, the 90% floor, strict all-r dominance,
40 min/4 GB, the frozen MiCall base and seven original images/results, or the
shared reserve.

## Worker priority

- P1 has first claim on the shared benchmark worker. PX and remap may backfill
  only when no eligible P1 experiment is queued.
- Finish the current arm naturally; never kill it to preempt. The coordinator
  grants P1 a contiguous session, not a new grant per case. The existing shared
  lease/guard and 32 GiB reserve remain. When a P1 job is immediately ready,
  drain PX at the next case boundary. No idle holding when no eligible P1 job
  exists.

## Two lanes

- **DEVELOPMENT (nonqualifying):** rapid native synthetic experiments and small
  integrated comparisons with the frozen MiCall images. Uses the existing
  native runner and OS resource limits; no OCI image build is required. Native
  scores are diagnostic only and are never reported as final MiCall scores. No
  truth/reference inputs to assembly. Preserve immutable attempt inputs,
  binary hash, argv, outcome, timing, output hash and distinct posthoc scoring;
  no elaborate new attestations. The existing 40 min/4 GB cap, shared reserve,
  one benchmark worker and no concurrent timing arms still apply; stricter
  existing native caps are fine. No global guard bypass, no frozen edits.
- **FORMAL qualification:** full 464 synthetic + 198 physical cases with exact
  provenance, frozen comparator evidence, and all existing floors plus all-r
  score/runtime gates. Formal physical regression and all-r qualification stay
  mandatory.

## Ownership

One coordinator, one persistent science owner who owns the candidate queue and
results through execution (not merely PR preparation), and one owner per
algorithm change. Stop duplicate audits/report-only agents and unnecessary new
policy layers. Use existing focused tests before a development experiment; use
CI and independent source review for formal integration. Report concrete
results, not PR count.

## Experiment discipline

- Use a short, predetermined, stratified native panel of roughly 2-3 cases
  each of PCR jackpot, equal strains, coverage hole, complex mixture,
  minority, clonal and discordant controls, including historical problem and
  held-out control cases. Use existing tools/data, with no new framework.
- Compare each proposed algorithm change **separately** against
  `950fe331`/current best, with alternating arm order; combine only measured
  winners. Reserve a holdout panel and evaluate it after decisions, never
  optimizing toward truth or known test sequences.
- Report combined and individual abundant-truth violations (explicitly labeled
  native proxies), regressions, runtime, failures and the number of real
  experiments.

## Integrated path

Run the small integrated frozen-MiCall panel as soon as an existing safe
build/deployment permits; do not let formal image admission block native
science. Whenever a promising candidate passes that panel, continue a full
464-case prospective run, targeting at least once every 24 h when feasible;
keep the current full run resumable and do not rerun an unchanged candidate.
A matched runtime diagnostic may guide work but is not acceptance evidence;
do not build further proof machinery unless it blocks a concrete needed run.

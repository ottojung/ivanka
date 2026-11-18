# Intent 010: Never write to cfe-lab/MiCall

**Status: binding immediately for every human, agent, script and workflow.**

Treat **`https://github.com/cfe-lab/MiCall` as strictly read-only**.
**Never push anything to, or create a pull request for, the
`cfe-lab/MiCall` GitHub repository.** This prohibition is unconditional:
no exception for bug fixes, benchmark experiments, refactors, clinical
validation, routine maintenance, or changes already tested elsewhere.

Prohibited actions include:

- Pushing any commit, branch, tag, ref, force-push or GitHub release;
  creating or updating pull requests; attempting a PR from a fork
  whose **base** is `cfe-lab/MiCall`.
- Writing through GitHub tools, API calls, `gh`, Git over SSH/HTTPS,
  automation, CI credentials, helper agents, alternate remotes,
  automated upstream synchronization that writes to the upstream, or
  transitive third-party tooling.
- Changing upstream repository content or its write-side configuration
  by any other method.

Read-only operations such as cloning, fetching upstream history,
inspecting published code/PRs/issues, and comparing commits are
permitted. Upstream can serve as a historical technical reference;
**this does not grant permission to change the benchmark's frozen
MiCall base or fix MiCall in the fork**. The current benchmark uses the
previously pinned integrations in [`ottojung/MiCall`](https://github.com/ottojung/MiCall)
under [Intent 011](011-ottojung-micall-fork-provenance.md) and the
[unconditional frozen-base rule](../bench/frozen-micall-base.md).

## Guardrails and verification

1. Document `cfe-lab/MiCall` as **fetch-only** when a Git upstream
   remote is configured: set its push URL to a deliberately invalid
   destination and do not install write credentials for it. Prefer
   `ottojung/MiCall` as the **sole writable repository destination**.
2. The frozen benchmark permits **no MiCall source mutations, patch PRs
   or replacement clinical builds at all**, including in the fork.
   For permitted read-only repository/API operations, verify the
   repository identity. Independently refuse all write destinations
   resolving to `cfe-lab/MiCall` (regardless of capitalization or transport).
3. Make CI/agent preflight fail if a documented automated publish
   destination or write remote points at the upstream. Add regression
   tests checking remote URL and PR target normalization, including
   `https://`, `ssh://` and `git@github.com:` variants, casing
   differences and accidental upstream pushes.
4. Historical upstream PRs may be inspected, but **never** reopened,
   updated or superseded with a new upstream PR. Link to the fork's
   commit/PR when discussing a fix.

**Acceptance:** no new upstream write or upstream-targeted PR is
ever attempted, and the repository-operations guard refuses the
upstream as a destination. The fork is **not** an exception to
the frozen MiCall benchmark base: no MiCall fixes are allowed. This intent does not restrict writing to the
separate `ottojung/ivanka` repository, nor does it weaken any
scientific or qualification requirement.

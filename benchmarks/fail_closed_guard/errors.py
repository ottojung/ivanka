"""Fail-closed errors. Every reason is a terminal benchmark FAILURE."""


class GuardExceeded(Exception):
    """Unsafe or over-budget observation; never reinterpret as success.

    Evidence gathered before the breach travels with the exception: the peak
    sample is genuine measured data and the exact-CID teardown proof is the
    condition for releasing a durable lease. Neither may be discarded merely
    because the arm ended by a fail-closed reason.
    """

    def __init__(self, reason, *, peak_rss=None, guard_result=None,
                 teardown=None, teardown_error=None, identity_observation=None):
        super().__init__(reason)
        self.reason = reason
        self.peak_rss = peak_rss
        self.guard_result = guard_result
        self.teardown = teardown
        self.teardown_error = teardown_error
        # Bound-vs-observed identity at the moment of failure. Diagnostic only;
        # it never changes the fail-closed decision.
        self.identity_observation = identity_observation


class TeardownError(Exception):
    """Exact-CID cleanup could not be proven; the arm stays failed."""


class OrphanLease(Exception):
    """A prior owned resource is still alive; new admission must fail closed.

    The reconciliation report is attached so the caller can record exactly
    which lease/CID blocked admission. The guard never cleans up the resource:
    the owning worker (or operator) owns that teardown.
    """

    def __init__(self, report):
        self.report = report
        super().__init__("worker lease not clear; admission refused")


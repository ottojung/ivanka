"""Fail-closed errors. Every reason is a terminal benchmark FAILURE."""


class GuardExceeded(Exception):
    """Unsafe or over-budget observation; never reinterpret as success."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


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


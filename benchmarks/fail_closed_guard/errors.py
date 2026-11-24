"""Fail-closed errors. Every reason is a terminal benchmark FAILURE."""


class GuardExceeded(Exception):
    """Unsafe or over-budget observation; never reinterpret as success."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class TeardownError(Exception):
    """Exact-CID cleanup could not be proven; the arm stays failed."""

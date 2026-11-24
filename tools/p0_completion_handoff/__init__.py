"""Read-only P0 completion handoff watcher.

This package observes the terminal state of the supervised frozen-original P0
controller and, only when full 198-case evidence genuinely exists, preserves
the exact PR433 audit and PR435 decision outside the audited roots and records
a durable board notification with an explicit next action. It never launches a
benchmark worker, scores a case, or edits the controller, candidate or frozen
MiCall source.
"""

"""Minimal orchestrator for the RQ3 escrow testbed (runbook docs/07-runbook.md section 7 item 2).

Queue, assignment (a node never verifies its own job), transaction relay to the trajescrow
program, a timestamped event log of on-chain and off-chain events, and a per-provider reputation
record. Verification is delegated to ``python -m trajver.verify``; nothing is reimplemented here.
"""
__version__ = "0.1.0"

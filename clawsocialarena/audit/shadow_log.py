"""Privileged shadow log -- independent copy of the action stream for SAF scoring.

SAF dimension 1 (Action Recoverability) compares the primary ActionLog against
this shadow log. If the primary log is tampered or has missing records, the
shadow reveals the divergence.

Implementation note: ShadowLog reuses ActionLog's schema and hash-chain logic
unchanged; the difference is purely the database path and the conceptual role.
"""

from clawsocialarena.action_log import ActionLog


class ShadowLog(ActionLog):
    """Same persistence + hash-chain logic as ActionLog, with a distinct DB path."""

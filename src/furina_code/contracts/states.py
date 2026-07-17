"""Furina Code contracts — state machine definitions."""

from __future__ import annotations

from enum import Enum


class RunBindingStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    CLOSED = "closed"
    SUPERSEDED = "superseded"


class TaskDossierStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Phase(str, Enum):
    INTAKE = "intake"
    OBSERVE = "observe"
    DELIBERATE = "deliberate"
    AUTHORIZE = "authorize"
    ACT = "act"
    RECONCILE = "reconcile"
    VERIFY = "verify"
    ADJUDICATE = "adjudicate"
    TERMINAL = "terminal"


class Disposition(str, Enum):
    ACTIVE = "active"
    WAITING_USER = "waiting_user"
    EXTERNAL_BLOCKED = "external_blocked"
    PAUSED = "paused"
    RECOVERY_REVIEW = "recovery_review"
    MANUAL_INTERVENTION = "manual_intervention"
    TERMINAL = "terminal"


# Allowed transitions: (phase, disposition) -> set of (new_phase, new_disposition)
# Only structural transitions are allowed; gates are not implemented here.
ALLOWED_TRANSITIONS: dict[tuple[str, str], set[tuple[str, str]]] = {
    # From intake/active
    ("intake", "active"): {
        ("observe", "active"),
        ("intake", "waiting_user"),
        ("intake", "external_blocked"),
        ("intake", "paused"),
        ("intake", "manual_intervention"),
    },
    # From intake waiting/external/paused back to intake/active
    ("intake", "waiting_user"): {("intake", "active")},
    ("intake", "external_blocked"): {("intake", "active")},
    ("intake", "paused"): {("intake", "active")},
    # From observe/active
    ("observe", "active"): {
        ("deliberate", "active"),
        ("observe", "waiting_user"),
        ("observe", "external_blocked"),
        ("observe", "paused"),
    },
    ("observe", "waiting_user"): {("observe", "active")},
    ("observe", "external_blocked"): {("observe", "active")},
    ("observe", "paused"): {("observe", "active")},
    # From deliberate/active (P4 back edges: deliberate→observe, deliberate→verify)
    ("deliberate", "active"): {
        ("observe", "active"),
        ("authorize", "active"),
        ("verify", "active"),
        ("deliberate", "waiting_user"),
        ("deliberate", "external_blocked"),
        ("deliberate", "paused"),
    },
    ("deliberate", "waiting_user"): {("deliberate", "active")},
    ("deliberate", "external_blocked"): {("deliberate", "active")},
    ("deliberate", "paused"): {("deliberate", "active")},
    # From authorize/active (P4 back edge: authorize→deliberate)
    ("authorize", "active"): {
        ("deliberate", "active"),
        ("act", "active"),
        ("authorize", "waiting_user"),
        ("authorize", "external_blocked"),
        ("authorize", "paused"),
    },
    ("authorize", "waiting_user"): {("authorize", "active")},
    ("authorize", "external_blocked"): {("authorize", "active")},
    ("authorize", "paused"): {("authorize", "active")},
    # From act/active (act→reconcile preserved)
    ("act", "active"): {
        ("reconcile", "active"),
        ("reconcile", "recovery_review"),
        ("act", "waiting_user"),
        ("act", "external_blocked"),
        ("act", "paused"),
    },
    ("act", "waiting_user"): {("act", "active")},
    ("act", "external_blocked"): {("act", "active")},
    ("act", "paused"): {("act", "active")},
    # From reconcile/active (P4 back edge: reconcile→deliberate)
    ("reconcile", "active"): {
        ("deliberate", "active"),
        ("verify", "active"),
        ("reconcile", "recovery_review"),
        ("reconcile", "waiting_user"),
        ("reconcile", "external_blocked"),
        ("reconcile", "paused"),
    },
    ("reconcile", "waiting_user"): {("reconcile", "active")},
    ("reconcile", "external_blocked"): {("reconcile", "active")},
    ("reconcile", "paused"): {("reconcile", "active")},
    # From verify/active (P4 back edge: verify→deliberate, verify→adjudicate preserved)
    ("verify", "active"): {
        ("deliberate", "active"),
        ("adjudicate", "active"),
        ("verify", "waiting_user"),
        ("verify", "external_blocked"),
        ("verify", "paused"),
    },
    ("verify", "waiting_user"): {("verify", "active")},
    ("verify", "external_blocked"): {("verify", "active")},
    ("verify", "paused"): {("verify", "active")},
    # From adjudicate/active (P4 back edge: adjudicate→deliberate)
    ("adjudicate", "active"): {
        ("deliberate", "active"),
        ("terminal", "terminal"),
        ("adjudicate", "waiting_user"),
        ("adjudicate", "external_blocked"),
        ("adjudicate", "paused"),
    },
    ("adjudicate", "waiting_user"): {("adjudicate", "active")},
    ("adjudicate", "external_blocked"): {("adjudicate", "active")},
    ("adjudicate", "paused"): {("adjudicate", "active")},
    # Recovery is deliberately narrow in E6.  A RecoveryVerdict is required
    # before leaving recovery_review; no transition here can replay an action.
    ("reconcile", "recovery_review"): {
        ("reconcile", "active"),
        ("reconcile", "paused"),
        ("reconcile", "manual_intervention"),
        ("terminal", "terminal"),
    },
    # Manual intervention — no automatic return
    ("intake", "manual_intervention"): set(),
    ("observe", "manual_intervention"): set(),
    ("deliberate", "manual_intervention"): set(),
    ("authorize", "manual_intervention"): set(),
    ("act", "manual_intervention"): set(),
    ("reconcile", "manual_intervention"): set(),
    ("verify", "manual_intervention"): set(),
    ("adjudicate", "manual_intervention"): set(),
}


def is_valid_transition(
    current_phase: str,
    current_disposition: str,
    new_phase: str,
    new_disposition: str,
) -> bool:
    key = (current_phase, current_disposition)
    allowed = ALLOWED_TRANSITIONS.get(key, None)
    if allowed is None:
        return False
    return (new_phase, new_disposition) in allowed

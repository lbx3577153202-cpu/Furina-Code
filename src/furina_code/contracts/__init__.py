"""Furina Code contracts package."""

from .errors import (
    FurinaContractError,
    ContractInvalid,
    AuthorityViolation,
    BindingMismatch,
    RevisionConflict,
    StateTransitionInvalid,
    IntegrityCheckFailed,
    LedgerWriteFailed,
)
from .meta import CanonicalMeta, SCHEMA_VERSION, now_utc, compute_integrity_ref
from .objects import RunBinding, TaskDossier, TaskRun, Checkpoint, OWNER_MAP, check_owner
from .states import Phase, Disposition, RunBindingStatus, TaskDossierStatus

__all__ = [
    "FurinaContractError",
    "ContractInvalid",
    "AuthorityViolation",
    "BindingMismatch",
    "RevisionConflict",
    "StateTransitionInvalid",
    "IntegrityCheckFailed",
    "LedgerWriteFailed",
    "CanonicalMeta",
    "SCHEMA_VERSION",
    "now_utc",
    "compute_integrity_ref",
    "RunBinding",
    "TaskDossier",
    "TaskRun",
    "Checkpoint",
    "OWNER_MAP",
    "check_owner",
    "Phase",
    "Disposition",
    "RunBindingStatus",
    "TaskDossierStatus",
]

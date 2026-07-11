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
from .meta import CanonicalMeta, SCHEMA_VERSION, now_utc, compute_integrity_ref, canonical_json_dumps
from .objects import (
    RunBinding, TaskDossier, TaskRun, Checkpoint,
    BackendProfile, ContextEnvelope, CandidateEnvelope, ProjectSnapshot,
    EvidenceEnvelope, VerificationPlan, VerificationVerdict, CompletionVerdict,
    OWNER_MAP, check_owner,
)
from .states import Phase, Disposition, RunBindingStatus, TaskDossierStatus, is_valid_transition

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
    "canonical_json_dumps",
    "RunBinding",
    "TaskDossier",
    "TaskRun",
    "Checkpoint",
    "BackendProfile",
    "ContextEnvelope",
    "CandidateEnvelope",
    "ProjectSnapshot",
    "EvidenceEnvelope",
    "VerificationPlan",
    "VerificationVerdict",
    "CompletionVerdict",
    "OWNER_MAP",
    "check_owner",
    "Phase",
    "Disposition",
    "RunBindingStatus",
    "TaskDossierStatus",
    "is_valid_transition",
]

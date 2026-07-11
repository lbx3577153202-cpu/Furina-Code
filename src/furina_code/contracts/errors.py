"""Furina Code contracts — errors."""


class FurinaContractError(Exception):
    """Base error for all contract violations."""

    def __init__(self, code: str, message: str, details: dict | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{code}] {message}")


class ContractInvalid(FurinaContractError):
    """Input does not match the contract."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("CONTRACT_INVALID", message, details)


class AuthorityViolation(FurinaContractError):
    """Caller is not the OWNER of the object type."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("AUTHORITY_VIOLATION", message, details)


class BindingMismatch(FurinaContractError):
    """RunBinding ID does not match."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("BINDING_MISMATCH", message, details)


class RevisionConflict(FurinaContractError):
    """expected_revision does not match current revision."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("REVISION_CONFLICT", message, details)


class StateTransitionInvalid(FurinaContractError):
    """TaskRun state transition is not allowed."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("STATE_TRANSITION_INVALID", message, details)


class IntegrityCheckFailed(FurinaContractError):
    """Stored integrity_ref does not match recomputed hash."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("INTEGRITY_CHECK_FAILED", message, details)


class LedgerWriteFailed(FurinaContractError):
    """Ledger could not complete the write."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__("LEDGER_WRITE_FAILED", message, details)

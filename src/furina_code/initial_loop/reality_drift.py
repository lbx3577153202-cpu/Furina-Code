"""B4: Reality drift detection and evidence invalidation.

After a successful verified write, externally mutating the target must
invalidate old VerificationVerdict and CompletionVerdict, preventing
them from being used for experience promotion or completed claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..contracts import (
    CompletionVerdict,
    ContractInvalid,
    VerificationVerdict,
)

if TYPE_CHECKING:
    from ..ledger import Ledger


@dataclass(frozen=True)
class DriftInvalidationResult:
    """Result of detecting and invalidating drifted evidence."""
    original_verification_ref: str
    original_completion_ref: str
    new_verification_ref: str
    new_completion_ref: str
    invalidation_reason: str


def detect_and_invalidate_reality_drift(
    ledger: Ledger,
    verification: VerificationVerdict,
    completion: CompletionVerdict,
    current_target_hash: str,
    expected_target_hash: str,
) -> DriftInvalidationResult:
    """Detect reality drift and invalidate old evidence.

    If the current target hash differs from what was verified, the old
    VerificationVerdict and CompletionVerdict are superseded with new
    revisions that mark them as invalidated.
    """
    from ..world.controlled_write import write_e5_object

    if current_target_hash == expected_target_hash:
        raise ContractInvalid("No reality drift detected; nothing to invalidate")

    reason = (
        f"Project reality changed: expected {expected_target_hash[:16]}... "
        f"but found {current_target_hash[:16]}..."
    )

    # Invalidate the VerificationVerdict
    new_verification = verification.invalidate_for_reality_change(reason)
    write_e5_object(ledger, new_verification, verification.meta.revision)

    # Invalidate the CompletionVerdict
    new_completion = completion.supersede_for_reality_change(
        new_verification.meta.integrity_ref, reason
    )
    write_e5_object(ledger, new_completion, completion.meta.revision)

    return DriftInvalidationResult(
        original_verification_ref=verification.meta.integrity_ref,
        original_completion_ref=completion.meta.integrity_ref,
        new_verification_ref=new_verification.meta.integrity_ref,
        new_completion_ref=new_completion.meta.integrity_ref,
        invalidation_reason=reason,
    )


def verify_old_evidence_invalid(
    ledger: Ledger,
    old_verification: "VerificationVerdict",
    old_completion: "CompletionVerdict",
) -> tuple[bool, bool]:
    """Check that old verification and completion have been superseded.

    Returns (verification_invalid, completion_invalid).
    """
    # After superseding, get_latest should return the NEW revision
    # which has outcome="not_run" / "not_completed"
    v_result = ledger.get_latest("VerificationVerdict", old_verification.meta.object_id)
    if v_result is None:
        return True, False

    c_result = ledger.get_latest("CompletionVerdict", old_completion.meta.object_id)
    if c_result is None:
        return False, True

    _, v_payload = v_result
    _, c_payload = c_result

    v_invalid = v_payload.get("outcome") in ("not_run", "fail")
    c_invalid = c_payload.get("outcome") == "not_completed"

    return v_invalid, c_invalid

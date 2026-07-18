"""B4: Reality drift detection and evidence invalidation.

After a successful verified write, the system must observe the real
filesystem and detect when the target has changed, then invalidate
old VerificationVerdict and CompletionVerdict.

Expected hash comes from BoundActionPlan.expected_diff, not from
VerificationVerdict.criterion_results.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from ..contracts import (
    BoundActionPlan,
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
    observed_hash: str
    expected_hash: str


def _safe_resolve(workspace: str, target_path: str) -> Path:
    """Resolve target path safely, rejecting escape and absolute paths."""
    p = PurePosixPath(target_path)
    if p.is_absolute():
        raise ContractInvalid(f"Absolute path rejected: {target_path}")
    if ".." in p.parts:
        raise ContractInvalid(f"Path traversal rejected: {target_path}")
    resolved = (Path(workspace) / target_path).resolve()
    workspace_resolved = Path(workspace).resolve()
    if not str(resolved).startswith(str(workspace_resolved)):
        raise ContractInvalid(f"Path escapes workspace: {target_path}")
    return resolved


def observe_target(workspace: str, target_path: str) -> str:
    """Observe the real filesystem and return current content hash."""
    target = _safe_resolve(workspace, target_path)
    if not target.is_file():
        return "deleted"
    actual_bytes = target.read_bytes()
    return "sha256:" + hashlib.sha256(actual_bytes).hexdigest()


def detect_and_invalidate_reality_drift(
    ledger: Ledger,
    verification: VerificationVerdict,
    completion: CompletionVerdict,
    plan: BoundActionPlan,
    workspace: str,
) -> DriftInvalidationResult:
    """Observe real filesystem, detect drift against plan, and invalidate.

    Expected hash comes from plan.expected_diff["content_sha256"].
    Observed hash comes from reading the actual file on disk.
    """
    from ..world.controlled_write import write_e5_object

    # Get target path and expected hash from the plan (persisted fact)
    target_path = plan.expected_diff.get("created_path", "")
    expected_hash = plan.expected_diff.get("content_sha256", "")
    if not target_path or not expected_hash:
        raise ContractInvalid("Plan missing target path or expected hash")

    # Observe the REAL filesystem
    observed_hash = observe_target(workspace, target_path)

    # Compare observed vs expected
    if observed_hash == expected_hash:
        raise ContractInvalid("No reality drift detected; target content unchanged")

    if observed_hash == "deleted":
        reason = f"Target file {target_path} was deleted after verification"
    else:
        reason = (
            f"Project reality changed: target {target_path} "
            f"expected {expected_hash[:16]}..., observed {observed_hash[:16]}..."
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
        observed_hash=observed_hash,
        expected_hash=expected_hash,
    )


def verify_old_evidence_invalid(
    ledger: Ledger,
    old_verification: VerificationVerdict,
    old_completion: CompletionVerdict,
) -> tuple[bool, bool]:
    """Check that old verification and completion have been superseded.

    Returns (verification_invalid, completion_invalid).
    """
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

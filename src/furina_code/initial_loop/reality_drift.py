"""B4: Reality drift detection and evidence invalidation.

After a successful verified write, the system must observe the real
filesystem and detect when the target has changed, then invalidate
old VerificationVerdict and CompletionVerdict.

Expected hash comes from BoundActionPlan.expected_diff.
Drift detection and experience extraction use Ledger current revision
as authority, not caller-provided objects.
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
    original_verification_ref: str
    original_completion_ref: str
    new_verification_ref: str
    new_completion_ref: str
    invalidation_reason: str
    observed_hash: str
    expected_hash: str


def _safe_resolve(workspace: str, target_path: str) -> Path:
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
    target = _safe_resolve(workspace, target_path)
    if not target.is_file():
        return "deleted"
    return "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()


def detect_and_invalidate_reality_drift(
    ledger: Ledger,
    plan: BoundActionPlan,
    workspace: str,
) -> DriftInvalidationResult:
    """Observe filesystem, detect drift, invalidate via ledger current revision.

    Queries ledger for current VerificationVerdict and CompletionVerdict
    rather than trusting caller-provided objects.
    """
    from ..world.controlled_write import write_e5_object

    target_path = plan.expected_diff.get("created_path", "")
    expected_hash = plan.expected_diff.get("content_sha256", "")
    if not target_path or not expected_hash:
        raise ContractInvalid("Plan missing target path or expected hash")

    observed_hash = observe_target(workspace, target_path)

    if observed_hash == expected_hash:
        raise ContractInvalid("No reality drift detected; target content unchanged")

    if observed_hash == "deleted":
        reason = f"Target file {target_path} was deleted after verification"
    else:
        reason = (
            f"Project reality changed: target {target_path} "
            f"expected {expected_hash[:16]}..., observed {observed_hash[:16]}..."
        )

    # Query ledger for current revision (authority)
    task_id = plan.meta.task_id
    run_binding_id = plan.meta.run_binding_id

    # Find current VerificationVerdict for this task
    v_objects = ledger.get_latest_for_binding(run_binding_id)
    current_verification = None
    current_completion = None
    for meta, payload in v_objects:
        if meta.object_type == "VerificationVerdict" and meta.task_id == task_id:
            current_verification = VerificationVerdict.create(
                meta.run_binding_id, meta.task_id, meta.task_run_id,
                meta.project_ref, meta.correlation_id,
                plan_ref=payload.get("plan_ref", ""),
                evidence_refs=tuple(payload.get("evidence_refs", [])),
                criterion_results=payload.get("criterion_results", {}),
                coverage=payload.get("coverage", 0.0),
                failed_checks=tuple(payload.get("failed_checks", [])),
                unknowns=tuple(payload.get("unknowns", [])),
                outcome=payload.get("outcome", ""),
                reason=payload.get("reason", ""),
            )
        if meta.object_type == "CompletionVerdict" and meta.task_id == task_id:
            current_completion = CompletionVerdict.create(
                meta.run_binding_id, meta.task_id, meta.task_run_id,
                meta.project_ref, meta.correlation_id,
                task_revision=payload.get("task_revision", 1),
                task_run_ref=payload.get("task_run_ref", ""),
                verification_ref=payload.get("verification_ref", ""),
                candidate_ref=payload.get("candidate_ref", ""),
                outcome=payload.get("outcome", ""),
                completed_items=tuple(payload.get("completed_items", [])),
                incomplete_items=tuple(payload.get("incomplete_items", [])),
                unverified_items=tuple(payload.get("unverified_items", [])),
                residual_risks=tuple(payload.get("residual_risks", [])),
                no_project_side_effect=payload.get("no_project_side_effect", True),
                user_effect=payload.get("user_effect", ""),
                reconciliation_refs=tuple(payload.get("reconciliation_refs", [])),
                action_plan_ref=payload.get("action_plan_ref"),
            )

    if current_verification is None or current_completion is None:
        raise ContractInvalid("No verification or completion found for this task in ledger")

    # Validate reference chain: completion -> verification
    # Use ledger-stored integrity_ref (from meta), not recomputed one
    v_integrity_ref = None
    for meta, payload in v_objects:
        if meta.object_type == "VerificationVerdict" and meta.task_id == task_id:
            v_integrity_ref = meta.integrity_ref

    if v_integrity_ref and current_completion.verification_ref != v_integrity_ref:
        raise ContractInvalid(
            "Completion verification_ref does not match current verification integrity_ref"
        )

    # Invalidate using ledger-current objects
    new_verification = current_verification.invalidate_for_reality_change(reason)
    write_e5_object(ledger, new_verification, current_verification.meta.revision)

    new_completion = current_completion.supersede_for_reality_change(
        new_verification.meta.integrity_ref, reason
    )
    write_e5_object(ledger, new_completion, current_completion.meta.revision)

    return DriftInvalidationResult(
        original_verification_ref=current_verification.meta.integrity_ref,
        original_completion_ref=current_completion.meta.integrity_ref,
        new_verification_ref=new_verification.meta.integrity_ref,
        new_completion_ref=new_completion.meta.integrity_ref,
        invalidation_reason=reason,
        observed_hash=observed_hash,
        expected_hash=expected_hash,
    )


def extract_experience_from_ledger(
    ledger: Ledger,
    run_binding_id: str,
    task_id: str,
) -> CompletionVerdict:
    """Get current CompletionVerdict from ledger for experience extraction.

    Returns the ledger-current version, not any caller-provided object.
    """
    objects = ledger.get_latest_for_binding(run_binding_id)
    for meta, payload in objects:
        if meta.object_type == "CompletionVerdict" and meta.task_id == task_id:
            return CompletionVerdict.create(
                meta.run_binding_id, meta.task_id, meta.task_run_id,
                meta.project_ref, meta.correlation_id,
                task_revision=payload.get("task_revision", 1),
                task_run_ref=payload.get("task_run_ref", ""),
                verification_ref=payload.get("verification_ref", ""),
                candidate_ref=payload.get("candidate_ref", ""),
                outcome=payload.get("outcome", ""),
                completed_items=tuple(payload.get("completed_items", [])),
                incomplete_items=tuple(payload.get("incomplete_items", [])),
                unverified_items=tuple(payload.get("unverified_items", [])),
                residual_risks=tuple(payload.get("residual_risks", [])),
                no_project_side_effect=payload.get("no_project_side_effect", True),
                user_effect=payload.get("user_effect", ""),
                reconciliation_refs=tuple(payload.get("reconciliation_refs", [])),
                action_plan_ref=payload.get("action_plan_ref"),
            )
    raise ContractInvalid(f"No CompletionVerdict found for task {task_id}")


def verify_old_evidence_invalid(
    ledger: Ledger,
    old_verification: VerificationVerdict,
    old_completion: CompletionVerdict,
) -> tuple[bool, bool]:
    """Check that old verification and completion have been superseded."""
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

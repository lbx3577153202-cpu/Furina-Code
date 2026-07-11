"""Furina Code contracts — formal domain objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .meta import CanonicalMeta, SCHEMA_VERSION, now_utc, compute_integrity_ref
from .states import (
    RunBindingStatus,
    TaskDossierStatus,
    Phase,
    Disposition,
    is_valid_transition,
)
from .errors import (
    ContractInvalid,
    AuthorityViolation,
    BindingMismatch,
    RevisionConflict,
    StateTransitionInvalid,
)


# --- OWNER mapping ---

OWNER_MAP: dict[str, str] = {
    # E3
    "RunBinding": "I1-A",
    "TaskDossier": "I2-A",
    "TaskRun": "I2-D",
    "Checkpoint": "I1-C",
    # E4
    "BackendProfile": "I2-B",
    "ContextEnvelope": "I2-C",
    "CandidateEnvelope": "I2-D",
    "ProjectSnapshot": "I3-A",
    "EvidenceEnvelope": "I4-C",
    "VerificationPlan": "I4-D",
    "VerificationVerdict": "I4-D",
    "CompletionVerdict": "I4-E",
}


def check_owner(object_type: str, caller_organ: str, declared_owner: str) -> None:
    expected = OWNER_MAP.get(object_type)
    if expected is None:
        raise ContractInvalid(f"Unknown object type: {object_type}")
    if declared_owner != expected:
        raise AuthorityViolation(
            f"Object {object_type} owner_organ={declared_owner} != expected {expected}",
            {"object_type": object_type, "declared": declared_owner, "expected": expected},
        )
    if caller_organ != expected:
        raise AuthorityViolation(
            f"Caller {caller_organ} is not OWNER {expected} of {object_type}",
            {"caller_organ": caller_organ, "expected": expected, "object_type": object_type},
        )


# --- Internal helpers ---

def _build_meta_and_integrity(
    object_type: str,
    object_id: str,
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    payload: dict[str, Any],
) -> tuple[CanonicalMeta, str]:
    """Build CanonicalMeta and compute integrity for a revision-1 object."""
    now = now_utc()
    owner = OWNER_MAP[object_type]
    meta_fields = {
        "schema_version": SCHEMA_VERSION,
        "object_type": object_type,
        "object_id": object_id,
        "revision": 1,
        "owner_organ": owner,
        "run_binding_id": run_binding_id,
        "task_id": task_id,
        "task_run_id": task_run_id,
        "project_ref": project_ref,
        "correlation_id": correlation_id,
        "causation_ref": None,
        "created_at": now.isoformat(),
        "recorded_at": now.isoformat(),
        "classification": "project_internal",
        "supersedes_ref": None,
    }
    integrity = compute_integrity_ref(meta_fields, payload)
    meta = CanonicalMeta(
        schema_version=SCHEMA_VERSION,
        object_type=object_type,
        object_id=object_id,
        revision=1,
        owner_organ=owner,
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref=project_ref,
        correlation_id=correlation_id,
        causation_ref=None,
        created_at=now,
        recorded_at=now,
        classification="project_internal",
        integrity_ref=integrity,
        supersedes_ref=None,
    )
    return meta, integrity


def _check_object_type(obj: Any, expected_type: str) -> None:
    if obj.meta.object_type != expected_type:
        raise ContractInvalid(f"meta.object_type must be {expected_type}")
    if obj.meta.owner_organ != OWNER_MAP[expected_type]:
        raise AuthorityViolation(f"{expected_type} owner_organ mismatch")


# --- RunBinding ---

@dataclass(frozen=True)
class RunBinding:
    meta: CanonicalMeta
    subject_ref: str
    user_ref: str
    project_ref: str
    task_ref: str
    allowed_tool_classes: tuple[str, ...]
    status: RunBindingStatus
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _check_object_type(self, "RunBinding")

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        subject_ref: str,
        user_ref: str,
        task_ref: str,
        allowed_tool_classes: tuple[str, ...],
        source_refs: tuple[str, ...],
    ) -> RunBinding:
        payload = {
            "subject_ref": subject_ref,
            "user_ref": user_ref,
            "project_ref": project_ref,
            "task_ref": task_ref,
            "allowed_tool_classes": list(allowed_tool_classes),
            "status": RunBindingStatus.ACTIVE.value,
            "source_refs": list(source_refs),
        }
        meta, _ = _build_meta_and_integrity(
            "RunBinding", run_binding_id, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
        )
        return RunBinding(
            meta=meta, subject_ref=subject_ref, user_ref=user_ref,
            project_ref=project_ref, task_ref=task_ref,
            allowed_tool_classes=allowed_tool_classes,
            status=RunBindingStatus.ACTIVE, source_refs=source_refs,
        )


# --- TaskDossier ---

@dataclass(frozen=True)
class TaskDossier:
    meta: CanonicalMeta
    source_intent_ref: str
    structured_goal: str
    success_criteria: tuple[str, ...]
    scope: tuple[str, ...]
    exclusions: tuple[str, ...]
    unknowns: tuple[str, ...]
    risk_class: str
    user_constraints: tuple[str, ...]
    status: TaskDossierStatus

    def __post_init__(self) -> None:
        _check_object_type(self, "TaskDossier")

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        source_intent_ref: str,
        structured_goal: str,
        success_criteria: tuple[str, ...],
        scope: tuple[str, ...],
        exclusions: tuple[str, ...],
        unknowns: tuple[str, ...],
        risk_class: str,
        user_constraints: tuple[str, ...],
    ) -> TaskDossier:
        payload = {
            "source_intent_ref": source_intent_ref,
            "structured_goal": structured_goal,
            "success_criteria": list(success_criteria),
            "scope": list(scope),
            "exclusions": list(exclusions),
            "unknowns": list(unknowns),
            "risk_class": risk_class,
            "user_constraints": list(user_constraints),
            "status": TaskDossierStatus.ACTIVE.value,
        }
        meta, _ = _build_meta_and_integrity(
            "TaskDossier", task_id, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
        )
        return TaskDossier(
            meta=meta, source_intent_ref=source_intent_ref,
            structured_goal=structured_goal, success_criteria=success_criteria,
            scope=scope, exclusions=exclusions, unknowns=unknowns,
            risk_class=risk_class, user_constraints=user_constraints,
            status=TaskDossierStatus.ACTIVE,
        )


# --- TaskRun ---

@dataclass(frozen=True)
class TaskRun:
    meta: CanonicalMeta
    task_revision: int
    phase: Phase
    disposition: Disposition
    current_refs: tuple[str, ...]
    open_requests: tuple[str, ...]
    started_at: datetime
    terminal_reason: str | None

    def __post_init__(self) -> None:
        _check_object_type(self, "TaskRun")

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        task_revision: int,
    ) -> TaskRun:
        now = now_utc()
        payload = {
            "task_revision": task_revision,
            "phase": Phase.INTAKE.value,
            "disposition": Disposition.ACTIVE.value,
            "current_refs": [],
            "open_requests": [],
            "started_at": now.isoformat(),
            "terminal_reason": None,
        }
        meta, _ = _build_meta_and_integrity(
            "TaskRun", task_run_id, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
        )
        return TaskRun(
            meta=meta, task_revision=task_revision,
            phase=Phase.INTAKE, disposition=Disposition.ACTIVE,
            current_refs=(), open_requests=(),
            started_at=now, terminal_reason=None,
        )

    def transition(
        self,
        caller_organ: str,
        new_phase: Phase,
        new_disposition: Disposition,
        correlation_id: str | None = None,
        recovery_verdict_ref: str | None = None,
        *,
        current_refs: tuple[str, ...] | None = None,
        open_requests: tuple[str, ...] | None = None,
        terminal_reason: str | None = None,
    ) -> TaskRun:
        check_owner("TaskRun", caller_organ, self.meta.owner_organ)

        if not is_valid_transition(
            self.phase.value, self.disposition.value,
            new_phase.value, new_disposition.value,
        ):
            raise StateTransitionInvalid(
                f"Cannot transition from {self.phase.value}/{self.disposition.value} "
                f"to {new_phase.value}/{new_disposition.value}",
                {
                    "current_phase": self.phase.value,
                    "current_disposition": self.disposition.value,
                    "new_phase": new_phase.value,
                    "new_disposition": new_disposition.value,
                },
            )

        now = now_utc()
        new_rev = self.meta.revision + 1
        corr = correlation_id or self.meta.correlation_id
        supersedes_ref = f"TaskRun:{self.meta.object_id}:rev{self.meta.revision}"
        resolved_refs = self.current_refs if current_refs is None else current_refs
        resolved_requests = self.open_requests if open_requests is None else open_requests
        resolved_reason = self.terminal_reason if terminal_reason is None else terminal_reason

        payload = {
            "task_revision": self.task_revision,
            "phase": new_phase.value,
            "disposition": new_disposition.value,
            "current_refs": list(resolved_refs),
            "open_requests": list(resolved_requests),
            "started_at": self.started_at.isoformat(),
            "terminal_reason": resolved_reason,
        }
        meta_fields = {
            "schema_version": SCHEMA_VERSION,
            "object_type": self.meta.object_type,
            "object_id": self.meta.object_id,
            "revision": new_rev,
            "owner_organ": self.meta.owner_organ,
            "run_binding_id": self.meta.run_binding_id,
            "task_id": self.meta.task_id,
            "task_run_id": self.meta.task_run_id,
            "project_ref": self.meta.project_ref,
            "correlation_id": corr,
            "causation_ref": supersedes_ref,
            "created_at": now.isoformat(),
            "recorded_at": now.isoformat(),
            "classification": "project_internal",
            "supersedes_ref": supersedes_ref,
        }
        integrity = compute_integrity_ref(meta_fields, payload)
        meta = CanonicalMeta(
            schema_version=SCHEMA_VERSION,
            object_type=self.meta.object_type,
            object_id=self.meta.object_id,
            revision=new_rev,
            owner_organ=self.meta.owner_organ,
            run_binding_id=self.meta.run_binding_id,
            task_id=self.meta.task_id,
            task_run_id=self.meta.task_run_id,
            project_ref=self.meta.project_ref,
            correlation_id=corr,
            causation_ref=supersedes_ref,
            created_at=now,
            recorded_at=now,
            classification="project_internal",
            integrity_ref=integrity,
            supersedes_ref=supersedes_ref,
        )
        return TaskRun(
            meta=meta, task_revision=self.task_revision,
            phase=new_phase, disposition=new_disposition,
            current_refs=resolved_refs, open_requests=resolved_requests,
            started_at=self.started_at, terminal_reason=resolved_reason,
        )


# --- Checkpoint ---

@dataclass(frozen=True)
class Checkpoint:
    meta: CanonicalMeta
    task_revision: int
    phase: Phase
    disposition: Disposition
    event_cursor: int
    pending_requests: tuple[str, ...]
    pending_actions: tuple[str, ...]
    snapshot_ref: str | None
    ticket_refs: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        _check_object_type(self, "Checkpoint")
        if self.pending_actions:
            raise ContractInvalid("Checkpoint.pending_actions must be empty")
        if self.ticket_refs:
            raise ContractInvalid("Checkpoint.ticket_refs must be empty")

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        task_revision: int,
        phase: Phase,
        disposition: Disposition,
        event_cursor: int,
        pending_requests: tuple[str, ...],
        snapshot_ref: str | None,
        reason: str,
    ) -> Checkpoint:
        now = now_utc()
        payload = {
            "task_revision": task_revision,
            "phase": phase.value,
            "disposition": disposition.value,
            "event_cursor": event_cursor,
            "pending_requests": list(pending_requests),
            "pending_actions": [],
            "snapshot_ref": snapshot_ref,
            "ticket_refs": [],
            "reason": reason,
        }
        object_id = f"{task_id}:checkpoint:{task_revision}"
        meta, _ = _build_meta_and_integrity(
            "Checkpoint", object_id, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
        )
        return Checkpoint(
            meta=meta, task_revision=task_revision,
            phase=phase, disposition=disposition,
            event_cursor=event_cursor, pending_requests=pending_requests,
            pending_actions=(), snapshot_ref=snapshot_ref,
            ticket_refs=(), reason=reason,
        )


# --- E4 Objects ---

@dataclass(frozen=True)
class BackendProfile:
    meta: CanonicalMeta
    backend_id: str
    backend_kind: str
    capabilities: tuple[str, ...]
    timeout_seconds: int
    status: str

    def __post_init__(self) -> None:
        _check_object_type(self, "BackendProfile")

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        backend_id: str,
        backend_kind: str,
        capabilities: tuple[str, ...],
        timeout_seconds: int,
    ) -> BackendProfile:
        payload = {
            "backend_id": backend_id,
            "backend_kind": backend_kind,
            "capabilities": list(capabilities),
            "timeout_seconds": timeout_seconds,
            "status": "active",
        }
        meta, _ = _build_meta_and_integrity(
            "BackendProfile", backend_id, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
        )
        return BackendProfile(
            meta=meta, backend_id=backend_id, backend_kind=backend_kind,
            capabilities=capabilities, timeout_seconds=timeout_seconds,
            status="active",
        )


@dataclass(frozen=True)
class ContextEnvelope:
    meta: CanonicalMeta
    snapshot_ref: str
    task_dossier_ref: str
    context_payload: dict[str, Any]
    instruction_profile_id: str
    instruction_profile_version: str

    def __post_init__(self) -> None:
        _check_object_type(self, "ContextEnvelope")

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        snapshot_ref: str,
        task_dossier_ref: str,
        context_payload: dict[str, Any],
        envelope_id: str | None = None,
    ) -> ContextEnvelope:
        payload = {
            "snapshot_ref": snapshot_ref,
            "task_dossier_ref": task_dossier_ref,
            "context_payload": context_payload,
            "instruction_profile_id": "e4-repository-baseline-v1",
            "instruction_profile_version": "1.0",
        }
        oid = envelope_id or f"{task_id}:context:1"
        meta, _ = _build_meta_and_integrity(
            "ContextEnvelope", oid, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
        )
        return ContextEnvelope(
            meta=meta, snapshot_ref=snapshot_ref,
            task_dossier_ref=task_dossier_ref,
            context_payload=context_payload,
            instruction_profile_id="e4-repository-baseline-v1",
            instruction_profile_version="1.0",
        )


@dataclass(frozen=True)
class CandidateEnvelope:
    meta: CanonicalMeta
    context_envelope_ref: str
    candidate_path: str
    candidate_sha256: str
    backend_id: str
    received_at: datetime

    def __post_init__(self) -> None:
        _check_object_type(self, "CandidateEnvelope")

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        context_envelope_ref: str,
        candidate_path: str,
        candidate_sha256: str,
        backend_id: str,
        envelope_id: str | None = None,
    ) -> CandidateEnvelope:
        now = now_utc()
        payload = {
            "context_envelope_ref": context_envelope_ref,
            "candidate_path": candidate_path,
            "candidate_sha256": candidate_sha256,
            "backend_id": backend_id,
            "received_at": now.isoformat(),
        }
        oid = envelope_id or f"{task_id}:candidate:1"
        meta, _ = _build_meta_and_integrity(
            "CandidateEnvelope", oid, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
        )
        return CandidateEnvelope(
            meta=meta, context_envelope_ref=context_envelope_ref,
            candidate_path=candidate_path, candidate_sha256=candidate_sha256,
            backend_id=backend_id, received_at=now,
        )


@dataclass(frozen=True)
class ProjectSnapshot:
    meta: CanonicalMeta
    head_sha: str
    branch: str
    status_lines: tuple[str, ...]
    tracked_count: int
    untracked_count: int
    is_clean: bool
    pyproject_exists: bool
    pyproject_sha256: str | None
    requires_python: str | None
    runtime_deps: tuple[str, ...]
    dev_deps: tuple[str, ...]
    pytest_testpaths: tuple[str, ...]
    ci_config_exists: bool
    ci_config_sha256: str | None
    blind_spots: tuple[str, ...]
    snapshot_sha256: str
    observed_at: datetime

    def __post_init__(self) -> None:
        _check_object_type(self, "ProjectSnapshot")

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        *,
        head_sha: str,
        branch: str,
        status_lines: tuple[str, ...],
        tracked_count: int,
        untracked_count: int,
        is_clean: bool,
        pyproject_exists: bool,
        pyproject_sha256: str | None,
        requires_python: str | None,
        runtime_deps: tuple[str, ...],
        dev_deps: tuple[str, ...],
        pytest_testpaths: tuple[str, ...],
        ci_config_exists: bool,
        ci_config_sha256: str | None,
        blind_spots: tuple[str, ...],
        snapshot_sha256: str,
        snapshot_id: str | None = None,
    ) -> ProjectSnapshot:
        now = now_utc()
        payload = {
            "head_sha": head_sha,
            "branch": branch,
            "status_lines": list(status_lines),
            "tracked_count": tracked_count,
            "untracked_count": untracked_count,
            "is_clean": is_clean,
            "pyproject_exists": pyproject_exists,
            "pyproject_sha256": pyproject_sha256,
            "requires_python": requires_python,
            "runtime_deps": list(runtime_deps),
            "dev_deps": list(dev_deps),
            "pytest_testpaths": list(pytest_testpaths),
            "ci_config_exists": ci_config_exists,
            "ci_config_sha256": ci_config_sha256,
            "blind_spots": list(blind_spots),
            "snapshot_sha256": snapshot_sha256,
            "observed_at": now.isoformat(),
        }
        oid = snapshot_id or f"{task_id}:snapshot:1"
        meta, _ = _build_meta_and_integrity(
            "ProjectSnapshot", oid, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
        )
        return ProjectSnapshot(
            meta=meta, head_sha=head_sha, branch=branch,
            status_lines=status_lines, tracked_count=tracked_count,
            untracked_count=untracked_count, is_clean=is_clean,
            pyproject_exists=pyproject_exists, pyproject_sha256=pyproject_sha256,
            requires_python=requires_python, runtime_deps=runtime_deps,
            dev_deps=dev_deps, pytest_testpaths=pytest_testpaths,
            ci_config_exists=ci_config_exists, ci_config_sha256=ci_config_sha256,
            blind_spots=blind_spots, snapshot_sha256=snapshot_sha256,
            observed_at=now,
        )


@dataclass(frozen=True)
class EvidenceEnvelope:
    meta: CanonicalMeta
    evidence_type: str
    source_ref: str
    claim: str
    supporting_refs: tuple[str, ...]
    integrity_status: str
    missing_evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        _check_object_type(self, "EvidenceEnvelope")

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        evidence_type: str,
        source_ref: str,
        claim: str,
        supporting_refs: tuple[str, ...] = (),
        integrity_status: str = "verified",
        missing_evidence: tuple[str, ...] = (),
        envelope_id: str | None = None,
    ) -> EvidenceEnvelope:
        payload = {
            "evidence_type": evidence_type,
            "source_ref": source_ref,
            "claim": claim,
            "supporting_refs": list(supporting_refs),
            "integrity_status": integrity_status,
            "missing_evidence": list(missing_evidence),
        }
        oid = envelope_id or f"{task_id}:evidence:1"
        meta, _ = _build_meta_and_integrity(
            "EvidenceEnvelope", oid, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
        )
        return EvidenceEnvelope(
            meta=meta, evidence_type=evidence_type,
            source_ref=source_ref, claim=claim,
            supporting_refs=supporting_refs,
            integrity_status=integrity_status,
            missing_evidence=missing_evidence,
        )


@dataclass(frozen=True)
class VerificationPlan:
    meta: CanonicalMeta
    candidate_ref: str
    success_criteria: tuple[str, ...]
    steps: tuple[str, ...]

    def __post_init__(self) -> None:
        _check_object_type(self, "VerificationPlan")

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        candidate_ref: str,
        success_criteria: tuple[str, ...],
        steps: tuple[str, ...],
        envelope_id: str | None = None,
    ) -> VerificationPlan:
        payload = {
            "candidate_ref": candidate_ref,
            "success_criteria": list(success_criteria),
            "steps": list(steps),
        }
        oid = envelope_id or f"{task_id}:vplan:1"
        meta, _ = _build_meta_and_integrity(
            "VerificationPlan", oid, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
        )
        return VerificationPlan(
            meta=meta, candidate_ref=candidate_ref,
            success_criteria=success_criteria, steps=steps,
        )


@dataclass(frozen=True)
class VerificationVerdict:
    meta: CanonicalMeta
    plan_ref: str
    outcome: str  # "pass" | "fail" | "inconclusive"
    checked_conditions: tuple[str, ...]
    supporting_refs: tuple[str, ...]
    failed_conditions: tuple[str, ...]
    checked_at: datetime

    def __post_init__(self) -> None:
        _check_object_type(self, "VerificationVerdict")

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        plan_ref: str,
        outcome: str,
        checked_conditions: tuple[str, ...],
        supporting_refs: tuple[str, ...] = (),
        failed_conditions: tuple[str, ...] = (),
        envelope_id: str | None = None,
    ) -> VerificationVerdict:
        now = now_utc()
        payload = {
            "plan_ref": plan_ref,
            "outcome": outcome,
            "checked_conditions": list(checked_conditions),
            "supporting_refs": list(supporting_refs),
            "failed_conditions": list(failed_conditions),
            "checked_at": now.isoformat(),
        }
        oid = envelope_id or f"{task_id}:vverdict:1"
        meta, _ = _build_meta_and_integrity(
            "VerificationVerdict", oid, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
        )
        return VerificationVerdict(
            meta=meta, plan_ref=plan_ref, outcome=outcome,
            checked_conditions=checked_conditions,
            supporting_refs=supporting_refs,
            failed_conditions=failed_conditions,
            checked_at=now,
        )


@dataclass(frozen=True)
class CompletionVerdict:
    meta: CanonicalMeta
    task_run_ref: str
    candidate_ref: str
    outcome: str  # "completed" | "failed" | "partial"
    completed_items: tuple[str, ...]
    incomplete_items: tuple[str, ...]
    unverified_items: tuple[str, ...]
    residual_risks: tuple[str, ...]
    user_effect: str

    def __post_init__(self) -> None:
        _check_object_type(self, "CompletionVerdict")

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        task_run_ref: str,
        candidate_ref: str,
        outcome: str,
        completed_items: tuple[str, ...] = (),
        incomplete_items: tuple[str, ...] = (),
        unverified_items: tuple[str, ...] = (),
        residual_risks: tuple[str, ...] = (),
        user_effect: str = "",
        envelope_id: str | None = None,
    ) -> CompletionVerdict:
        payload = {
            "task_run_ref": task_run_ref,
            "candidate_ref": candidate_ref,
            "outcome": outcome,
            "completed_items": list(completed_items),
            "incomplete_items": list(incomplete_items),
            "unverified_items": list(unverified_items),
            "residual_risks": list(residual_risks),
            "user_effect": user_effect,
        }
        oid = envelope_id or f"{task_id}:cverdict:1"
        meta, _ = _build_meta_and_integrity(
            "CompletionVerdict", oid, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
        )
        return CompletionVerdict(
            meta=meta, task_run_ref=task_run_ref,
            candidate_ref=candidate_ref, outcome=outcome,
            completed_items=completed_items,
            incomplete_items=incomplete_items,
            unverified_items=unverified_items,
            residual_risks=residual_risks,
            user_effect=user_effect,
        )

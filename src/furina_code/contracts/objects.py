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
    "RecoveryVerdict": "I1-C",
    # E4
    "BackendProfile": "I2-B",
    "ContextEnvelope": "I2-C",
    "CandidateEnvelope": "I2-D",
    "ProjectSnapshot": "I3-A",
    "EvidenceEnvelope": "I4-C",
    "VerificationPlan": "I4-D",
    "VerificationVerdict": "I4-D",
    "CompletionVerdict": "I4-E",
    # E5
    "BoundActionPlan": "I3-B",
    "ActionReceipt": "I3-C",
    "RealityReconciliation": "I3-D",
    "AuthorizationDecision": "I4-A",
    "AuthorizationTicket": "I4-B",
    "EnforcementVerdict": "I4-B",
    # E7
    "ExperienceCandidate": "I5-A",
    "ExperienceMatch": "I5-B",
    "TrialUseRecord": "I5-B",
    "ExperienceLifecycleVerdict": "I5-C",
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
    *,
    causation_ref: str | None = None,
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
        "causation_ref": causation_ref,
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
        causation_ref=causation_ref,
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


def _revise_meta(meta: CanonicalMeta, payload: dict[str, Any]) -> CanonicalMeta:
    """Build the next immutable revision for a formal object."""
    now = now_utc()
    revision = meta.revision + 1
    supersedes_ref = f"{meta.object_type}:{meta.object_id}:rev{meta.revision}"
    fields = {
        "schema_version": SCHEMA_VERSION,
        "object_type": meta.object_type,
        "object_id": meta.object_id,
        "revision": revision,
        "owner_organ": meta.owner_organ,
        "run_binding_id": meta.run_binding_id,
        "task_id": meta.task_id,
        "task_run_id": meta.task_run_id,
        "project_ref": meta.project_ref,
        "correlation_id": meta.correlation_id,
        "causation_ref": supersedes_ref,
        "created_at": now.isoformat(),
        "recorded_at": now.isoformat(),
        "classification": meta.classification,
        "supersedes_ref": supersedes_ref,
    }
    return CanonicalMeta(
        schema_version=SCHEMA_VERSION, object_type=meta.object_type,
        object_id=meta.object_id, revision=revision, owner_organ=meta.owner_organ,
        run_binding_id=meta.run_binding_id, task_id=meta.task_id,
        task_run_id=meta.task_run_id, project_ref=meta.project_ref,
        correlation_id=meta.correlation_id, causation_ref=supersedes_ref,
        created_at=now, recorded_at=now, classification=meta.classification,
        integrity_ref=compute_integrity_ref(fields, payload),
        supersedes_ref=supersedes_ref,
    )


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
        causation_ref: str | None = None,
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
            causation_ref=causation_ref,
        )
        return TaskDossier(
            meta=meta, source_intent_ref=source_intent_ref,
            structured_goal=structured_goal, success_criteria=success_criteria,
            scope=scope, exclusions=exclusions, unknowns=unknowns,
            risk_class=risk_class, user_constraints=user_constraints,
            status=TaskDossierStatus.ACTIVE,
        )

    def revise(
        self,
        *,
        structured_goal: str,
        success_criteria: tuple[str, ...],
        scope: tuple[str, ...],
        exclusions: tuple[str, ...],
        unknowns: tuple[str, ...],
        risk_class: str,
        user_constraints: tuple[str, ...],
        source_intent_ref: str | None = None,
    ) -> TaskDossier:
        """Preserve the prior intent record while making a user correction explicit."""
        payload = {
            "source_intent_ref": source_intent_ref or self.source_intent_ref,
            "structured_goal": structured_goal,
            "success_criteria": list(success_criteria), "scope": list(scope),
            "exclusions": list(exclusions), "unknowns": list(unknowns),
            "risk_class": risk_class, "user_constraints": list(user_constraints),
            "status": TaskDossierStatus.ACTIVE.value,
        }
        return TaskDossier(
            meta=_revise_meta(self.meta, payload),
            source_intent_ref=source_intent_ref or self.source_intent_ref,
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
        causation_ref: str | None = None,
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
            causation_ref=causation_ref,
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

        if self.disposition == Disposition.RECOVERY_REVIEW and not recovery_verdict_ref:
            raise StateTransitionInvalid(
                "Leaving recovery_review requires a RecoveryVerdict reference",
                {"current_phase": self.phase.value, "new_phase": new_phase.value},
            )

        now = now_utc()
        new_rev = self.meta.revision + 1
        corr = correlation_id or self.meta.correlation_id
        supersedes_ref = f"TaskRun:{self.meta.object_id}:rev{self.meta.revision}"
        resolved_refs = self.current_refs if current_refs is None else current_refs
        # Recovery is a causal decision, not merely a parameter used to open a
        # state-machine edge.  Preserve it in the new TaskRun revision so a
        # rebuilt continuity view can explain why execution resumed.
        if recovery_verdict_ref and recovery_verdict_ref not in resolved_refs:
            resolved_refs = (*resolved_refs, recovery_verdict_ref)
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
            "causation_ref": recovery_verdict_ref or supersedes_ref,
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
            causation_ref=recovery_verdict_ref or supersedes_ref,
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
        pending_actions: tuple[str, ...] = (),
        ticket_refs: tuple[str, ...] = (),
        causation_ref: str | None = None,
    ) -> Checkpoint:
        now = now_utc()
        payload = {
            "task_revision": task_revision,
            "phase": phase.value,
            "disposition": disposition.value,
            "event_cursor": event_cursor,
            "pending_requests": list(pending_requests),
            "pending_actions": list(pending_actions),
            "snapshot_ref": snapshot_ref,
            "ticket_refs": list(ticket_refs),
            "reason": reason,
        }
        object_id = f"{task_id}:checkpoint:{task_revision}"
        meta, _ = _build_meta_and_integrity(
            "Checkpoint", object_id, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
            causation_ref=causation_ref,
        )
        return Checkpoint(
            meta=meta, task_revision=task_revision,
            phase=phase, disposition=disposition,
            event_cursor=event_cursor, pending_requests=pending_requests,
            pending_actions=pending_actions, snapshot_ref=snapshot_ref,
            ticket_refs=ticket_refs, reason=reason,
        )


# --- E6 recovery ---

_RECOVERY_OUTCOMES = frozenset({
    "continue_no_replay", "skip_confirmed_action", "retry_confirmed_not_applied",
    "compensate", "pause", "manual_intervention", "cancel",
})


@dataclass(frozen=True)
class RecoveryVerdict:
    meta: CanonicalMeta
    checkpoint_ref: str
    fresh_snapshot_refs: tuple[str, ...]
    receipt_refs: tuple[str, ...]
    ticket_review: str
    outcome: str
    resume_phase: Phase | None
    required_steps: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        _check_object_type(self, "RecoveryVerdict")
        if self.outcome not in _RECOVERY_OUTCOMES:
            raise ContractInvalid(f"Invalid RecoveryVerdict outcome: {self.outcome}")

    @staticmethod
    def create(
        run_binding_id: str, task_id: str, task_run_id: str, project_ref: str,
        correlation_id: str, checkpoint_ref: str, fresh_snapshot_refs: tuple[str, ...],
        receipt_refs: tuple[str, ...], ticket_review: str, outcome: str,
        resume_phase: Phase | None, required_steps: tuple[str, ...], reason: str,
        verdict_id: str | None = None, causation_ref: str | None = None,
    ) -> RecoveryVerdict:
        payload = {
            "checkpoint_ref": checkpoint_ref,
            "fresh_snapshot_refs": list(fresh_snapshot_refs),
            "receipt_refs": list(receipt_refs), "ticket_review": ticket_review,
            "outcome": outcome,
            "resume_phase": resume_phase.value if resume_phase else None,
            "required_steps": list(required_steps), "reason": reason,
        }
        oid = verdict_id or f"{task_id}:recovery-verdict:1"
        meta, _ = _build_meta_and_integrity(
            "RecoveryVerdict", oid, run_binding_id, task_id, task_run_id,
            project_ref, correlation_id, payload, causation_ref=causation_ref,
        )
        return RecoveryVerdict(meta, checkpoint_ref, fresh_snapshot_refs, receipt_refs,
                               ticket_review, outcome, resume_phase, required_steps, reason)


# --- E4 Objects ---

@dataclass(frozen=True)
class BackendProfile:
    meta: CanonicalMeta
    provider_ref: str
    capabilities: tuple[str, ...]
    limits: dict[str, Any]
    health: str
    credential_mode: str
    data_policy_ref: str
    last_checked_at: datetime
    backend_id: str
    backend_kind: str

    def __post_init__(self) -> None:
        _check_object_type(self, "BackendProfile")

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        provider_ref: str,
        capabilities: tuple[str, ...],
        limits: dict[str, Any] | None = None,
        health: str = "available",
        credential_mode: str = "none",
        data_policy_ref: str = "local-only",
        backend_id: str = "local-cli",
        backend_kind: str = "local",
        causation_ref: str | None = None,
    ) -> BackendProfile:
        now = now_utc()
        _limits = limits or {}
        payload = {
            "provider_ref": provider_ref,
            "capabilities": list(capabilities),
            "limits": _limits,
            "health": health,
            "credential_mode": credential_mode,
            "data_policy_ref": data_policy_ref,
            "last_checked_at": now.isoformat(),
            "backend_id": backend_id,
            "backend_kind": backend_kind,
        }
        meta, _ = _build_meta_and_integrity(
            "BackendProfile", backend_id, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
            causation_ref=causation_ref,
        )
        return BackendProfile(
            meta=meta, provider_ref=provider_ref,
            capabilities=capabilities, limits=_limits,
            health=health, credential_mode=credential_mode,
            data_policy_ref=data_policy_ref, last_checked_at=now,
            backend_id=backend_id, backend_kind=backend_kind,
        )


@dataclass(frozen=True)
class ContextEnvelope:
    meta: CanonicalMeta
    task_revision: int
    purpose: str
    snapshot_ref: str
    task_dossier_ref: str
    included_refs: tuple[str, ...]
    redactions: tuple[str, ...]
    classification_summary: str
    disclosure_basis: str
    backend_ref: str
    instruction_profile: dict[str, str]
    context_digest: str
    context_payload: dict[str, Any]

    def __post_init__(self) -> None:
        _check_object_type(self, "ContextEnvelope")

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        task_revision: int,
        purpose: str,
        snapshot_ref: str,
        task_dossier_ref: str,
        included_refs: tuple[str, ...],
        redactions: tuple[str, ...],
        classification_summary: str,
        disclosure_basis: str,
        backend_ref: str,
        context_digest: str,
        context_payload: dict[str, Any] | None = None,
        envelope_id: str | None = None,
        causation_ref: str | None = None,
    ) -> ContextEnvelope:
        _ctx = context_payload or {}
        payload = {
            "task_revision": task_revision,
            "purpose": purpose,
            "snapshot_ref": snapshot_ref,
            "task_dossier_ref": task_dossier_ref,
            "included_refs": list(included_refs),
            "redactions": list(redactions),
            "classification_summary": classification_summary,
            "disclosure_basis": disclosure_basis,
            "backend_ref": backend_ref,
            "instruction_profile": {"id": "e4-repository-baseline-v1", "version": "1.0"},
            "context_digest": context_digest,
            "context_payload": _ctx,
        }
        oid = envelope_id or f"{task_id}:context:1"
        meta, _ = _build_meta_and_integrity(
            "ContextEnvelope", oid, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
            causation_ref=causation_ref,
        )
        return ContextEnvelope(
            meta=meta, task_revision=task_revision, purpose=purpose,
            snapshot_ref=snapshot_ref, task_dossier_ref=task_dossier_ref,
            included_refs=included_refs, redactions=redactions,
            classification_summary=classification_summary,
            disclosure_basis=disclosure_basis, backend_ref=backend_ref,
            instruction_profile={"id": "e4-repository-baseline-v1", "version": "1.0"},
            context_digest=context_digest,
            context_payload=_ctx,
        )


@dataclass(frozen=True)
class CandidateEnvelope:
    meta: CanonicalMeta
    candidate_type: str
    backend_profile_ref: str
    backend_session_ref: str
    context_ref: str
    content_ref: str
    candidate_digest: str
    claimed_assumptions: tuple[str, ...]
    requested_actions: tuple[str, ...]
    received_at: datetime
    status: str

    def __post_init__(self) -> None:
        _check_object_type(self, "CandidateEnvelope")

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        candidate_type: str,
        backend_profile_ref: str,
        backend_session_ref: str,
        context_ref: str,
        content_ref: str,
        candidate_digest: str,
        claimed_assumptions: tuple[str, ...] = (),
        requested_actions: tuple[str, ...] = (),
        envelope_id: str | None = None,
        causation_ref: str | None = None,
    ) -> CandidateEnvelope:
        now = now_utc()
        payload = {
            "candidate_type": candidate_type,
            "backend_profile_ref": backend_profile_ref,
            "backend_session_ref": backend_session_ref,
            "context_ref": context_ref,
            "content_ref": content_ref,
            "candidate_digest": candidate_digest,
            "claimed_assumptions": list(claimed_assumptions),
            "requested_actions": list(requested_actions),
            "received_at": now.isoformat(),
            "status": "accepted",
        }
        oid = envelope_id or f"{task_id}:candidate:1"
        meta, _ = _build_meta_and_integrity(
            "CandidateEnvelope", oid, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
            causation_ref=causation_ref,
        )
        return CandidateEnvelope(
            meta=meta, candidate_type=candidate_type,
            backend_profile_ref=backend_profile_ref,
            backend_session_ref=backend_session_ref,
            context_ref=context_ref, content_ref=content_ref,
            candidate_digest=candidate_digest,
            claimed_assumptions=claimed_assumptions,
            requested_actions=requested_actions,
            received_at=now, status="accepted",
        )


@dataclass(frozen=True)
class ProjectSnapshot:
    meta: CanonicalMeta
    observation_scope: str
    git_ref: dict[str, Any]
    file_facts: dict[str, Any]
    environment_facts: dict[str, Any]
    blind_spots: tuple[str, ...]
    observed_at: datetime
    freshness_policy: str
    # Extended fields for detailed observation
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
    snapshot_sha256: str

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
        causation_ref: str | None = None,
    ) -> ProjectSnapshot:
        now = now_utc()
        observation_scope = "read-only repository baseline"
        git_ref = {"head_sha": head_sha, "branch": branch, "is_clean": is_clean}
        file_facts = {
            "tracked_count": tracked_count,
            "untracked_count": untracked_count,
            "pyproject_exists": pyproject_exists,
            "pyproject_sha256": pyproject_sha256,
        }
        environment_facts = {
            "requires_python": requires_python,
            "runtime_deps": list(runtime_deps),
            "dev_deps": list(dev_deps),
            "pytest_testpaths": list(pytest_testpaths),
            "ci_config_exists": ci_config_exists,
            "ci_config_sha256": ci_config_sha256,
        }
        freshness_policy = "point-in-time"
        payload = {
            "observation_scope": observation_scope,
            "git_ref": git_ref,
            "file_facts": file_facts,
            "environment_facts": environment_facts,
            "blind_spots": list(blind_spots),
            "observed_at": now.isoformat(),
            "freshness_policy": freshness_policy,
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
        }
        oid = snapshot_id or f"{task_id}:snapshot:1"
        meta, _ = _build_meta_and_integrity(
            "ProjectSnapshot", oid, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
            causation_ref=causation_ref,
        )
        return ProjectSnapshot(
            meta=meta, observation_scope=observation_scope,
            git_ref=git_ref, file_facts=file_facts,
            environment_facts=environment_facts,
            blind_spots=blind_spots, observed_at=now,
            freshness_policy=freshness_policy,
            head_sha=head_sha, branch=branch,
            status_lines=status_lines, tracked_count=tracked_count,
            untracked_count=untracked_count, is_clean=is_clean,
            pyproject_exists=pyproject_exists, pyproject_sha256=pyproject_sha256,
            requires_python=requires_python, runtime_deps=runtime_deps,
            dev_deps=dev_deps, pytest_testpaths=pytest_testpaths,
            ci_config_exists=ci_config_exists, ci_config_sha256=ci_config_sha256,
            snapshot_sha256=snapshot_sha256,
        )


# --- E5 controlled-write objects ---

_TICKET_STATUSES = frozenset({"active", "consumed", "revoked", "expired", "invalidated"})
_RECEIPT_STATUSES = frozenset({"executing", "applied", "not_applied", "outcome_unknown"})
_RECONCILIATION_VERDICTS = frozenset({"expected", "divergent", "unknown"})


@dataclass(frozen=True)
class BoundActionPlan:
    meta: CanonicalMeta
    candidate_ref: str
    task_revision: int
    baseline_snapshot_ref: str
    baseline_snapshot_sha256: str
    target_scope: tuple[str, ...]
    operations: tuple[dict[str, Any], ...]
    expected_diff: dict[str, Any]
    risk: str
    rollback_or_compensation: str
    preconditions: tuple[str, ...]
    experience_match_ref: str | None

    def __post_init__(self) -> None:
        _check_object_type(self, "BoundActionPlan")
        if not self.operations:
            raise ContractInvalid("BoundActionPlan.operations must not be empty")
        if not self.target_scope:
            raise ContractInvalid("BoundActionPlan.target_scope must not be empty")

    @staticmethod
    def create(
        run_binding_id: str, task_id: str, task_run_id: str, project_ref: str,
        correlation_id: str, candidate_ref: str, task_revision: int,
        baseline_snapshot_ref: str, baseline_snapshot_sha256: str,
        target_scope: tuple[str, ...], operations: tuple[dict[str, Any], ...],
        expected_diff: dict[str, Any], risk: str,
        rollback_or_compensation: str, preconditions: tuple[str, ...],
        experience_match_ref: str | None = None,
        plan_id: str | None = None, causation_ref: str | None = None,
    ) -> BoundActionPlan:
        payload = {
            "candidate_ref": candidate_ref, "task_revision": task_revision,
            "baseline_snapshot_ref": baseline_snapshot_ref,
            "baseline_snapshot_sha256": baseline_snapshot_sha256,
            "target_scope": list(target_scope), "operations": list(operations),
            "expected_diff": expected_diff, "risk": risk,
            "rollback_or_compensation": rollback_or_compensation,
            "preconditions": list(preconditions),
            "experience_match_ref": experience_match_ref,
        }
        oid = plan_id or f"{task_id}:action-plan:1"
        meta, _ = _build_meta_and_integrity(
            "BoundActionPlan", oid, run_binding_id, task_id, task_run_id,
            project_ref, correlation_id, payload, causation_ref=causation_ref,
        )
        return BoundActionPlan(meta, candidate_ref, task_revision, baseline_snapshot_ref,
                               baseline_snapshot_sha256, target_scope, operations,
                               expected_diff, risk, rollback_or_compensation, preconditions,
                               experience_match_ref)


@dataclass(frozen=True)
class AuthorizationDecision:
    meta: CanonicalMeta
    subject_ref: str
    task_revision: int
    plan_ref: str
    snapshot_ref: str
    policy_version: str
    decision: str
    conditions: tuple[str, ...]
    reason: str
    user_authority_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _check_object_type(self, "AuthorizationDecision")
        if self.decision not in {"allow", "deny"}:
            raise ContractInvalid("AuthorizationDecision.decision must be allow or deny")

    @staticmethod
    def create(
        run_binding_id: str, task_id: str, task_run_id: str, project_ref: str,
        correlation_id: str, subject_ref: str, task_revision: int, plan_ref: str,
        snapshot_ref: str, policy_version: str, decision: str,
        conditions: tuple[str, ...], reason: str,
        user_authority_refs: tuple[str, ...], decision_id: str | None = None,
        causation_ref: str | None = None,
    ) -> AuthorizationDecision:
        payload = {
            "subject_ref": subject_ref, "task_revision": task_revision,
            "plan_ref": plan_ref, "snapshot_ref": snapshot_ref,
            "policy_version": policy_version, "decision": decision,
            "conditions": list(conditions), "reason": reason,
            "user_authority_refs": list(user_authority_refs),
        }
        oid = decision_id or f"{task_id}:authorization-decision:1"
        meta, _ = _build_meta_and_integrity(
            "AuthorizationDecision", oid, run_binding_id, task_id, task_run_id,
            project_ref, correlation_id, payload, causation_ref=causation_ref,
        )
        return AuthorizationDecision(meta, subject_ref, task_revision, plan_ref, snapshot_ref,
                                     policy_version, decision, conditions, reason,
                                     user_authority_refs)


@dataclass(frozen=True)
class AuthorizationTicket:
    meta: CanonicalMeta
    decision_ref: str
    plan_ref: str
    task_revision: int
    snapshot_ref: str
    scope: tuple[str, ...]
    valid_from: datetime
    expires_at: datetime
    single_use: bool
    status: str
    revocation_ref: str | None

    def __post_init__(self) -> None:
        _check_object_type(self, "AuthorizationTicket")
        if self.status not in _TICKET_STATUSES:
            raise ContractInvalid(f"Invalid AuthorizationTicket status: {self.status}")
        if not self.single_use:
            raise ContractInvalid("E5 AuthorizationTicket must be single_use")
        if self.expires_at <= self.valid_from:
            raise ContractInvalid("AuthorizationTicket expires_at must be after valid_from")

    @staticmethod
    def create(
        run_binding_id: str, task_id: str, task_run_id: str, project_ref: str,
        correlation_id: str, decision_ref: str, plan_ref: str, task_revision: int,
        snapshot_ref: str, scope: tuple[str, ...], valid_from: datetime,
        expires_at: datetime, ticket_id: str | None = None,
        causation_ref: str | None = None,
    ) -> AuthorizationTicket:
        payload = {
            "decision_ref": decision_ref, "plan_ref": plan_ref,
            "task_revision": task_revision, "snapshot_ref": snapshot_ref,
            "scope": list(scope), "valid_from": valid_from.isoformat(),
            "expires_at": expires_at.isoformat(), "single_use": True,
            "status": "active", "revocation_ref": None,
        }
        oid = ticket_id or f"{task_id}:authorization-ticket:1"
        meta, _ = _build_meta_and_integrity(
            "AuthorizationTicket", oid, run_binding_id, task_id, task_run_id,
            project_ref, correlation_id, payload, causation_ref=causation_ref,
        )
        return AuthorizationTicket(meta, decision_ref, plan_ref, task_revision, snapshot_ref,
                                   scope, valid_from, expires_at, True, "active", None)

    def consume(self) -> AuthorizationTicket:
        if self.status != "active":
            raise ContractInvalid("Only an active AuthorizationTicket may be consumed")
        payload = {
            "decision_ref": self.decision_ref, "plan_ref": self.plan_ref,
            "task_revision": self.task_revision, "snapshot_ref": self.snapshot_ref,
            "scope": list(self.scope), "valid_from": self.valid_from.isoformat(),
            "expires_at": self.expires_at.isoformat(), "single_use": self.single_use,
            "status": "consumed", "revocation_ref": self.revocation_ref,
        }
        return AuthorizationTicket(_revise_meta(self.meta, payload), self.decision_ref,
                                   self.plan_ref, self.task_revision, self.snapshot_ref,
                                   self.scope, self.valid_from, self.expires_at, self.single_use,
                                   "consumed", self.revocation_ref)


@dataclass(frozen=True)
class EnforcementVerdict:
    meta: CanonicalMeta
    ticket_ref: str
    plan_ref: str
    current_snapshot_ref: str
    decision: str
    checked_at: datetime
    reason: str

    def __post_init__(self) -> None:
        _check_object_type(self, "EnforcementVerdict")
        if self.decision not in {"allow", "deny"}:
            raise ContractInvalid("EnforcementVerdict.decision must be allow or deny")

    @staticmethod
    def create(
        run_binding_id: str, task_id: str, task_run_id: str, project_ref: str,
        correlation_id: str, ticket_ref: str, plan_ref: str,
        current_snapshot_ref: str, decision: str, reason: str,
        verdict_id: str | None = None, causation_ref: str | None = None,
    ) -> EnforcementVerdict:
        now = now_utc()
        payload = {"ticket_ref": ticket_ref, "plan_ref": plan_ref,
                   "current_snapshot_ref": current_snapshot_ref,
                   "decision": decision, "checked_at": now.isoformat(), "reason": reason}
        oid = verdict_id or f"{task_id}:enforcement:1"
        meta, _ = _build_meta_and_integrity(
            "EnforcementVerdict", oid, run_binding_id, task_id, task_run_id,
            project_ref, correlation_id, payload, causation_ref=causation_ref,
        )
        return EnforcementVerdict(meta, ticket_ref, plan_ref, current_snapshot_ref,
                                  decision, now, reason)


@dataclass(frozen=True)
class ActionReceipt:
    meta: CanonicalMeta
    plan_ref: str
    ticket_ref: str
    idempotency_key: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    tool_ref: str
    raw_result_ref: str | None
    exit_info: dict[str, Any]
    side_effect_assessment: str

    def __post_init__(self) -> None:
        _check_object_type(self, "ActionReceipt")
        if self.status not in _RECEIPT_STATUSES:
            raise ContractInvalid(f"Invalid ActionReceipt status: {self.status}")

    @staticmethod
    def create(
        run_binding_id: str, task_id: str, task_run_id: str, project_ref: str,
        correlation_id: str, plan_ref: str, ticket_ref: str, idempotency_key: str,
        tool_ref: str, receipt_id: str | None = None,
        causation_ref: str | None = None,
    ) -> ActionReceipt:
        now = now_utc()
        payload = {"plan_ref": plan_ref, "ticket_ref": ticket_ref,
                   "idempotency_key": idempotency_key, "status": "executing",
                   "started_at": now.isoformat(), "ended_at": None,
                   "tool_ref": tool_ref, "raw_result_ref": None,
                   "exit_info": {}, "side_effect_assessment": "execution_started"}
        oid = receipt_id or f"{task_id}:action-receipt:1"
        meta, _ = _build_meta_and_integrity(
            "ActionReceipt", oid, run_binding_id, task_id, task_run_id,
            project_ref, correlation_id, payload, causation_ref=causation_ref,
        )
        return ActionReceipt(meta, plan_ref, ticket_ref, idempotency_key, "executing",
                             now, None, tool_ref, None, {}, "execution_started")

    def finish(self, status: str, raw_result_ref: str | None,
               exit_info: dict[str, Any], side_effect_assessment: str) -> ActionReceipt:
        if self.status != "executing":
            raise ContractInvalid("Only an executing ActionReceipt may be finished")
        if status not in _RECEIPT_STATUSES - {"executing"}:
            raise ContractInvalid(f"Invalid terminal ActionReceipt status: {status}")
        now = now_utc()
        payload = {
            "plan_ref": self.plan_ref, "ticket_ref": self.ticket_ref,
            "idempotency_key": self.idempotency_key, "status": status,
            "started_at": self.started_at.isoformat(), "ended_at": now.isoformat(),
            "tool_ref": self.tool_ref, "raw_result_ref": raw_result_ref,
            "exit_info": exit_info, "side_effect_assessment": side_effect_assessment,
        }
        return ActionReceipt(_revise_meta(self.meta, payload), self.plan_ref, self.ticket_ref,
                             self.idempotency_key, status, self.started_at, now, self.tool_ref,
                             raw_result_ref, exit_info, side_effect_assessment)


@dataclass(frozen=True)
class RealityReconciliation:
    meta: CanonicalMeta
    plan_ref: str
    receipt_ref: str
    before_snapshot_ref: str
    after_snapshot_ref: str
    expected_diff: dict[str, Any]
    actual_diff: dict[str, Any]
    unexpected_changes: tuple[str, ...]
    verdict: str

    def __post_init__(self) -> None:
        _check_object_type(self, "RealityReconciliation")
        if self.verdict not in _RECONCILIATION_VERDICTS:
            raise ContractInvalid(f"Invalid RealityReconciliation verdict: {self.verdict}")

    @staticmethod
    def create(
        run_binding_id: str, task_id: str, task_run_id: str, project_ref: str,
        correlation_id: str, plan_ref: str, receipt_ref: str,
        before_snapshot_ref: str, after_snapshot_ref: str,
        expected_diff: dict[str, Any], actual_diff: dict[str, Any],
        unexpected_changes: tuple[str, ...], verdict: str,
        reconciliation_id: str | None = None,
        causation_ref: str | None = None,
    ) -> RealityReconciliation:
        payload = {
            "plan_ref": plan_ref, "receipt_ref": receipt_ref,
            "before_snapshot_ref": before_snapshot_ref,
            "after_snapshot_ref": after_snapshot_ref,
            "expected_diff": expected_diff, "actual_diff": actual_diff,
            "unexpected_changes": list(unexpected_changes), "verdict": verdict,
        }
        oid = reconciliation_id or f"{task_id}:reconciliation:1"
        meta, _ = _build_meta_and_integrity(
            "RealityReconciliation", oid, run_binding_id, task_id, task_run_id,
            project_ref, correlation_id, payload, causation_ref=causation_ref,
        )
        return RealityReconciliation(meta, plan_ref, receipt_ref, before_snapshot_ref,
                                     after_snapshot_ref, expected_diff, actual_diff,
                                     unexpected_changes, verdict)


@dataclass(frozen=True)
class EvidenceEnvelope:
    meta: CanonicalMeta
    claim_scope: str
    evidence_type: str
    source_ref: str
    claim: str
    source_refs: tuple[str, ...]
    causal_links: tuple[str, ...]
    supporting_refs: tuple[str, ...]
    integrity_status: str
    redactions: tuple[str, ...]
    retention_class: str
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
        claim_scope: str,
        evidence_type: str,
        source_ref: str,
        claim: str,
        source_refs: tuple[str, ...] = (),
        causal_links: tuple[str, ...] = (),
        supporting_refs: tuple[str, ...] = (),
        integrity_status: str = "verified",
        redactions: tuple[str, ...] = (),
        retention_class: str = "project_internal",
        missing_evidence: tuple[str, ...] = (),
        envelope_id: str | None = None,
        causation_ref: str | None = None,
    ) -> EvidenceEnvelope:
        payload = {
            "claim_scope": claim_scope,
            "evidence_type": evidence_type,
            "source_ref": source_ref,
            "claim": claim,
            "source_refs": list(source_refs),
            "causal_links": list(causal_links),
            "supporting_refs": list(supporting_refs),
            "integrity_status": integrity_status,
            "redactions": list(redactions),
            "retention_class": retention_class,
            "missing_evidence": list(missing_evidence),
        }
        oid = envelope_id or f"{task_id}:evidence:1"
        meta, _ = _build_meta_and_integrity(
            "EvidenceEnvelope", oid, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
            causation_ref=causation_ref,
        )
        return EvidenceEnvelope(
            meta=meta, claim_scope=claim_scope,
            evidence_type=evidence_type, source_ref=source_ref,
            claim=claim, source_refs=source_refs,
            causal_links=causal_links, supporting_refs=supporting_refs,
            integrity_status=integrity_status, redactions=redactions,
            retention_class=retention_class,
            missing_evidence=missing_evidence,
        )


@dataclass(frozen=True)
class VerificationPlan:
    meta: CanonicalMeta
    task_revision: int
    candidate_ref: str
    success_criteria_map: dict[str, str]
    success_criteria: tuple[str, ...]
    checks: tuple[str, ...]
    required_evidence: tuple[str, ...]
    independence_requirements: tuple[str, ...]
    stop_conditions: tuple[str, ...]
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
        task_revision: int,
        candidate_ref: str,
        success_criteria_map: dict[str, str],
        success_criteria: tuple[str, ...],
        checks: tuple[str, ...],
        required_evidence: tuple[str, ...] = (),
        independence_requirements: tuple[str, ...] = (),
        stop_conditions: tuple[str, ...] = (),
        envelope_id: str | None = None,
        causation_ref: str | None = None,
    ) -> VerificationPlan:
        payload = {
            "task_revision": task_revision,
            "candidate_ref": candidate_ref,
            "success_criteria_map": success_criteria_map,
            "success_criteria": list(success_criteria),
            "checks": list(checks),
            "required_evidence": list(required_evidence),
            "independence_requirements": list(independence_requirements),
            "stop_conditions": list(stop_conditions),
            "steps": list(checks),
        }
        oid = envelope_id or f"{task_id}:vplan:1"
        meta, _ = _build_meta_and_integrity(
            "VerificationPlan", oid, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
            causation_ref=causation_ref,
        )
        return VerificationPlan(
            meta=meta, task_revision=task_revision,
            candidate_ref=candidate_ref,
            success_criteria_map=success_criteria_map,
            success_criteria=success_criteria, checks=checks,
            required_evidence=required_evidence,
            independence_requirements=independence_requirements,
            stop_conditions=stop_conditions, steps=checks,
        )


_VALID_VERDICT_OUTCOMES = frozenset({"pass", "fail", "inconclusive", "not_run"})
_VALID_COMPLETION_OUTCOMES = frozenset({"completed", "partially_completed", "not_completed", "manual_decision_required", "cancelled"})


@dataclass(frozen=True)
class VerificationVerdict:
    meta: CanonicalMeta
    plan_ref: str
    evidence_refs: tuple[str, ...]
    criterion_results: dict[str, str]
    coverage: float
    failed_checks: tuple[str, ...]
    unknowns: tuple[str, ...]
    outcome: str
    reason: str
    checked_at: datetime

    def __post_init__(self) -> None:
        _check_object_type(self, "VerificationVerdict")
        if self.outcome not in _VALID_VERDICT_OUTCOMES:
            raise ContractInvalid(
                f"Invalid VerificationVerdict outcome: {self.outcome}",
                {"outcome": self.outcome, "valid": sorted(_VALID_VERDICT_OUTCOMES)},
            )

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        plan_ref: str,
        evidence_refs: tuple[str, ...],
        criterion_results: dict[str, str],
        coverage: float,
        failed_checks: tuple[str, ...] = (),
        unknowns: tuple[str, ...] = (),
        outcome: str = "not_run",
        reason: str = "",
        envelope_id: str | None = None,
        causation_ref: str | None = None,
    ) -> VerificationVerdict:
        now = now_utc()
        payload = {
            "plan_ref": plan_ref,
            "evidence_refs": list(evidence_refs),
            "criterion_results": criterion_results,
            "coverage": coverage,
            "failed_checks": list(failed_checks),
            "unknowns": list(unknowns),
            "outcome": outcome,
            "reason": reason,
            "checked_at": now.isoformat(),
        }
        oid = envelope_id or f"{task_id}:vverdict:1"
        meta, _ = _build_meta_and_integrity(
            "VerificationVerdict", oid, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
            causation_ref=causation_ref,
        )
        return VerificationVerdict(
            meta=meta, plan_ref=plan_ref,
            evidence_refs=evidence_refs,
            criterion_results=criterion_results,
            coverage=coverage, failed_checks=failed_checks,
            unknowns=unknowns, outcome=outcome, reason=reason,
            checked_at=now,
        )

    def invalidate_for_reality_change(self, reason: str) -> VerificationVerdict:
        """A changed project creates a new non-passing verdict; old evidence stays intact."""
        checked_at = now_utc()
        payload = {
            "plan_ref": self.plan_ref, "evidence_refs": list(self.evidence_refs),
            "criterion_results": self.criterion_results, "coverage": 0.0,
            "failed_checks": [], "unknowns": ["project_reality_changed"],
            "outcome": "not_run", "reason": reason,
            "checked_at": checked_at.isoformat(),
        }
        meta = _revise_meta(self.meta, payload)
        return VerificationVerdict(
            meta=meta, plan_ref=self.plan_ref, evidence_refs=self.evidence_refs,
            criterion_results=self.criterion_results, coverage=0.0,
            failed_checks=(), unknowns=("project_reality_changed",),
            outcome="not_run", reason=reason, checked_at=checked_at,
        )


@dataclass(frozen=True)
class CompletionVerdict:
    meta: CanonicalMeta
    task_revision: int
    task_run_ref: str
    verification_ref: str
    reconciliation_refs: tuple[str, ...]
    candidate_ref: str
    outcome: str
    completed_items: tuple[str, ...]
    incomplete_items: tuple[str, ...]
    unverified_items: tuple[str, ...]
    residual_risks: tuple[str, ...]
    no_project_side_effect: bool
    user_effect: str
    action_plan_ref: str | None

    def __post_init__(self) -> None:
        _check_object_type(self, "CompletionVerdict")
        if self.outcome not in _VALID_COMPLETION_OUTCOMES:
            raise ContractInvalid(
                f"Invalid CompletionVerdict outcome: {self.outcome}",
                {"outcome": self.outcome, "valid": sorted(_VALID_COMPLETION_OUTCOMES)},
            )

    @staticmethod
    def create(
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        task_revision: int,
        task_run_ref: str,
        verification_ref: str,
        candidate_ref: str,
        outcome: str,
        completed_items: tuple[str, ...] = (),
        incomplete_items: tuple[str, ...] = (),
        unverified_items: tuple[str, ...] = (),
        residual_risks: tuple[str, ...] = (),
        no_project_side_effect: bool = True,
        user_effect: str = "",
        reconciliation_refs: tuple[str, ...] = (),
        action_plan_ref: str | None = None,
        envelope_id: str | None = None,
        causation_ref: str | None = None,
    ) -> CompletionVerdict:
        payload = {
            "task_revision": task_revision,
            "task_run_ref": task_run_ref,
            "verification_ref": verification_ref,
            "reconciliation_refs": list(reconciliation_refs),
            "candidate_ref": candidate_ref,
            "outcome": outcome,
            "completed_items": list(completed_items),
            "incomplete_items": list(incomplete_items),
            "unverified_items": list(unverified_items),
            "residual_risks": list(residual_risks),
            "no_project_side_effect": no_project_side_effect,
            "user_effect": user_effect,
            "action_plan_ref": action_plan_ref,
        }
        oid = envelope_id or f"{task_id}:cverdict:1"
        meta, _ = _build_meta_and_integrity(
            "CompletionVerdict", oid, run_binding_id,
            task_id, task_run_id, project_ref, correlation_id, payload,
            causation_ref=causation_ref,
        )
        return CompletionVerdict(
            meta=meta, task_revision=task_revision,
            task_run_ref=task_run_ref, verification_ref=verification_ref,
            reconciliation_refs=reconciliation_refs,
            candidate_ref=candidate_ref, outcome=outcome,
            completed_items=completed_items,
            incomplete_items=incomplete_items,
            unverified_items=unverified_items,
            residual_risks=residual_risks,
            no_project_side_effect=no_project_side_effect,
            user_effect=user_effect, action_plan_ref=action_plan_ref,
        )

    def supersede_for_reality_change(self, verification_ref: str, reason: str) -> CompletionVerdict:
        """A past completed claim cannot survive a relevant project-state change."""
        payload = {
            "task_revision": self.task_revision, "task_run_ref": self.task_run_ref,
            "verification_ref": verification_ref,
            "reconciliation_refs": list(self.reconciliation_refs),
            "candidate_ref": self.candidate_ref, "outcome": "not_completed",
            "completed_items": [], "incomplete_items": list(self.completed_items),
            "unverified_items": list(self.completed_items),
            "residual_risks": [reason], "no_project_side_effect": self.no_project_side_effect,
            "user_effect": "previous completion superseded after project reality changed",
            "action_plan_ref": self.action_plan_ref,
        }
        return CompletionVerdict(
            meta=_revise_meta(self.meta, payload), task_revision=self.task_revision,
            task_run_ref=self.task_run_ref, verification_ref=verification_ref,
            reconciliation_refs=self.reconciliation_refs, candidate_ref=self.candidate_ref,
            outcome="not_completed", completed_items=(),
            incomplete_items=self.completed_items, unverified_items=self.completed_items,
            residual_risks=(reason,), no_project_side_effect=self.no_project_side_effect,
            user_effect="previous completion superseded after project reality changed",
            action_plan_ref=self.action_plan_ref,
        )


# --- E7 experience: candidates may influence later candidates, never authority ---

_EXPERIENCE_STATUSES = frozenset({
    "draft", "candidate", "trial_eligible", "under_trial", "reusable",
    "conditional", "degraded", "frozen", "retired",
})


@dataclass(frozen=True)
class ExperienceCandidate:
    meta: CanonicalMeta
    source_completion_refs: tuple[str, ...]
    success_and_failure_facts: tuple[str, ...]
    lesson: str
    applicability: tuple[str, ...]
    contraindications: tuple[str, ...]
    risk: str
    confidence: str
    status: str

    def __post_init__(self) -> None:
        _check_object_type(self, "ExperienceCandidate")
        if self.status not in _EXPERIENCE_STATUSES:
            raise ContractInvalid(f"Invalid ExperienceCandidate status: {self.status}")
        if self.status not in {"draft", "candidate", "trial_eligible"}:
            raise ContractInvalid("E7 can only create a non-promoted experience candidate")

    @staticmethod
    def create(
        run_binding_id: str, task_id: str, task_run_id: str, project_ref: str,
        correlation_id: str, source_completion_refs: tuple[str, ...],
        success_and_failure_facts: tuple[str, ...], lesson: str,
        applicability: tuple[str, ...], contraindications: tuple[str, ...],
        risk: str, confidence: str, status: str = "candidate",
        candidate_id: str | None = None, causation_ref: str | None = None,
    ) -> ExperienceCandidate:
        payload = {
            "source_completion_refs": list(source_completion_refs),
            "success_and_failure_facts": list(success_and_failure_facts),
            "lesson": lesson, "applicability": list(applicability),
            "contraindications": list(contraindications), "risk": risk,
            "confidence": confidence, "status": status,
        }
        oid = candidate_id or f"{task_id}:experience-candidate:1"
        meta, _ = _build_meta_and_integrity(
            "ExperienceCandidate", oid, run_binding_id, task_id, task_run_id,
            project_ref, correlation_id, payload, causation_ref=causation_ref,
        )
        return ExperienceCandidate(meta, source_completion_refs, success_and_failure_facts,
                                   lesson, applicability, contraindications, risk,
                                   confidence, status)


@dataclass(frozen=True)
class ExperienceMatch:
    meta: CanonicalMeta
    task_revision: int
    candidate_refs: tuple[str, ...]
    match_reasons: tuple[str, ...]
    mismatch_reasons: tuple[str, ...]
    risk_warnings: tuple[str, ...]
    recommendation: str

    def __post_init__(self) -> None:
        _check_object_type(self, "ExperienceMatch")

    @staticmethod
    def create(
        run_binding_id: str, task_id: str, task_run_id: str, project_ref: str,
        correlation_id: str, task_revision: int, candidate_refs: tuple[str, ...],
        match_reasons: tuple[str, ...], mismatch_reasons: tuple[str, ...],
        risk_warnings: tuple[str, ...], recommendation: str,
        match_id: str | None = None, causation_ref: str | None = None,
    ) -> ExperienceMatch:
        payload = {
            "task_revision": task_revision, "candidate_refs": list(candidate_refs),
            "match_reasons": list(match_reasons), "mismatch_reasons": list(mismatch_reasons),
            "risk_warnings": list(risk_warnings), "recommendation": recommendation,
        }
        oid = match_id or f"{task_id}:experience-match:1"
        meta, _ = _build_meta_and_integrity(
            "ExperienceMatch", oid, run_binding_id, task_id, task_run_id,
            project_ref, correlation_id, payload, causation_ref=causation_ref,
        )
        return ExperienceMatch(meta, task_revision, candidate_refs, match_reasons,
                               mismatch_reasons, risk_warnings, recommendation)


@dataclass(frozen=True)
class TrialUseRecord:
    meta: CanonicalMeta
    experience_ref: str
    task_revision: int
    usage_mode: str
    influence_ref: str
    completion_ref: str
    result: str

    def __post_init__(self) -> None:
        _check_object_type(self, "TrialUseRecord")
        if self.usage_mode != "candidate_guidance_only":
            raise ContractInvalid("Experience may only guide a candidate in E7")

    @staticmethod
    def create(
        run_binding_id: str, task_id: str, task_run_id: str, project_ref: str,
        correlation_id: str, experience_ref: str, task_revision: int,
        influence_ref: str, completion_ref: str, result: str,
        record_id: str | None = None, causation_ref: str | None = None,
    ) -> TrialUseRecord:
        payload = {
            "experience_ref": experience_ref, "task_revision": task_revision,
            "usage_mode": "candidate_guidance_only", "influence_ref": influence_ref,
            "completion_ref": completion_ref, "result": result,
        }
        oid = record_id or f"{task_id}:trial-use:1"
        meta, _ = _build_meta_and_integrity(
            "TrialUseRecord", oid, run_binding_id, task_id, task_run_id,
            project_ref, correlation_id, payload, causation_ref=causation_ref,
        )
        return TrialUseRecord(meta, experience_ref, task_revision, "candidate_guidance_only",
                              influence_ref, completion_ref, result)


@dataclass(frozen=True)
class ExperienceLifecycleVerdict:
    meta: CanonicalMeta
    experience_ref: str
    evidence_refs: tuple[str, ...]
    previous_status: str
    new_status: str
    reason: str
    user_revision_ref: str | None

    def __post_init__(self) -> None:
        _check_object_type(self, "ExperienceLifecycleVerdict")
        if self.previous_status not in _EXPERIENCE_STATUSES or self.new_status not in _EXPERIENCE_STATUSES:
            raise ContractInvalid("Invalid experience lifecycle status")
        if self.new_status == "reusable":
            raise ContractInvalid("E7's single second trial may not mark experience reusable")

    @staticmethod
    def create(
        run_binding_id: str, task_id: str, task_run_id: str, project_ref: str,
        correlation_id: str, experience_ref: str, evidence_refs: tuple[str, ...],
        previous_status: str, new_status: str, reason: str,
        user_revision_ref: str | None = None, verdict_id: str | None = None,
        causation_ref: str | None = None,
    ) -> ExperienceLifecycleVerdict:
        payload = {
            "experience_ref": experience_ref, "evidence_refs": list(evidence_refs),
            "previous_status": previous_status, "new_status": new_status,
            "reason": reason, "user_revision_ref": user_revision_ref,
        }
        oid = verdict_id or f"{task_id}:experience-lifecycle:1"
        meta, _ = _build_meta_and_integrity(
            "ExperienceLifecycleVerdict", oid, run_binding_id, task_id, task_run_id,
            project_ref, correlation_id, payload, causation_ref=causation_ref,
        )
        return ExperienceLifecycleVerdict(meta, experience_ref, evidence_refs,
                                          previous_status, new_status, reason,
                                          user_revision_ref)

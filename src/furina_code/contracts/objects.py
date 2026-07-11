"""Furina Code contracts — formal domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    RevisionConflict,
    StateTransitionInvalid,
)


# --- OWNER mapping ---

OWNER_MAP: dict[str, str] = {
    "RunBinding": "I1-A",
    "TaskDossier": "I2-A",
    "TaskRun": "I2-D",
    "Checkpoint": "I1-C",
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
        if self.meta.object_type != "RunBinding":
            raise ContractInvalid("meta.object_type must be RunBinding")
        if self.meta.owner_organ != OWNER_MAP["RunBinding"]:
            raise AuthorityViolation("RunBinding owner_organ mismatch")

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
        now = now_utc()
        payload = {
            "subject_ref": subject_ref,
            "user_ref": user_ref,
            "project_ref": project_ref,
            "task_ref": task_ref,
            "allowed_tool_classes": list(allowed_tool_classes),
            "status": RunBindingStatus.ACTIVE.value,
            "source_refs": list(source_refs),
        }
        meta_fields = {
            "schema_version": SCHEMA_VERSION,
            "object_type": "RunBinding",
            "object_id": run_binding_id,
            "revision": 1,
            "owner_organ": OWNER_MAP["RunBinding"],
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
            object_type="RunBinding",
            object_id=run_binding_id,
            revision=1,
            owner_organ=OWNER_MAP["RunBinding"],
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
        return RunBinding(
            meta=meta,
            subject_ref=subject_ref,
            user_ref=user_ref,
            project_ref=project_ref,
            task_ref=task_ref,
            allowed_tool_classes=allowed_tool_classes,
            status=RunBindingStatus.ACTIVE,
            source_refs=source_refs,
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
        if self.meta.object_type != "TaskDossier":
            raise ContractInvalid("meta.object_type must be TaskDossier")
        if self.meta.owner_organ != OWNER_MAP["TaskDossier"]:
            raise AuthorityViolation("TaskDossier owner_organ mismatch")

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
        now = now_utc()
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
        meta_fields = {
            "schema_version": SCHEMA_VERSION,
            "object_type": "TaskDossier",
            "object_id": task_id,
            "revision": 1,
            "owner_organ": OWNER_MAP["TaskDossier"],
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
            object_type="TaskDossier",
            object_id=task_id,
            revision=1,
            owner_organ=OWNER_MAP["TaskDossier"],
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
        return TaskDossier(
            meta=meta,
            source_intent_ref=source_intent_ref,
            structured_goal=structured_goal,
            success_criteria=success_criteria,
            scope=scope,
            exclusions=exclusions,
            unknowns=unknowns,
            risk_class=risk_class,
            user_constraints=user_constraints,
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
        if self.meta.object_type != "TaskRun":
            raise ContractInvalid("meta.object_type must be TaskRun")
        if self.meta.owner_organ != OWNER_MAP["TaskRun"]:
            raise AuthorityViolation("TaskRun owner_organ mismatch")

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
        meta_fields = {
            "schema_version": SCHEMA_VERSION,
            "object_type": "TaskRun",
            "object_id": task_run_id,
            "revision": 1,
            "owner_organ": OWNER_MAP["TaskRun"],
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
            object_type="TaskRun",
            object_id=task_run_id,
            revision=1,
            owner_organ=OWNER_MAP["TaskRun"],
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
        return TaskRun(
            meta=meta,
            task_revision=task_revision,
            phase=Phase.INTAKE,
            disposition=Disposition.ACTIVE,
            current_refs=(),
            open_requests=(),
            started_at=now,
            terminal_reason=None,
        )

    def transition(
        self,
        caller_organ: str,
        run_binding_id: str,
        task_id: str,
        task_run_id: str,
        project_ref: str,
        correlation_id: str,
        new_phase: Phase,
        new_disposition: Disposition,
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
        payload = {
            "task_revision": self.task_revision,
            "phase": new_phase.value,
            "disposition": new_disposition.value,
            "current_refs": list(self.current_refs),
            "open_requests": list(self.open_requests),
            "started_at": self.started_at.isoformat(),
            "terminal_reason": self.terminal_reason,
        }
        meta_fields = {
            "schema_version": SCHEMA_VERSION,
            "object_type": "TaskRun",
            "object_id": task_run_id,
            "revision": new_rev,
            "owner_organ": OWNER_MAP["TaskRun"],
            "run_binding_id": run_binding_id,
            "task_id": task_id,
            "task_run_id": task_run_id,
            "project_ref": project_ref,
            "correlation_id": correlation_id,
            "causation_ref": f"TaskRun:{task_run_id}:rev{self.meta.revision}",
            "created_at": now.isoformat(),
            "recorded_at": now.isoformat(),
            "classification": "project_internal",
            "supersedes_ref": f"TaskRun:{task_run_id}:rev{self.meta.revision}",
        }
        integrity = compute_integrity_ref(meta_fields, payload)
        meta = CanonicalMeta(
            schema_version=SCHEMA_VERSION,
            object_type="TaskRun",
            object_id=task_run_id,
            revision=new_rev,
            owner_organ=OWNER_MAP["TaskRun"],
            run_binding_id=run_binding_id,
            task_id=task_id,
            task_run_id=task_run_id,
            project_ref=project_ref,
            correlation_id=correlation_id,
            causation_ref=f"TaskRun:{task_run_id}:rev{self.meta.revision}",
            created_at=now,
            recorded_at=now,
            classification="project_internal",
            integrity_ref=integrity,
            supersedes_ref=f"TaskRun:{task_run_id}:rev{self.meta.revision}",
        )
        return TaskRun(
            meta=meta,
            task_revision=self.task_revision,
            phase=new_phase,
            disposition=new_disposition,
            current_refs=self.current_refs,
            open_requests=self.open_requests,
            started_at=self.started_at,
            terminal_reason=self.terminal_reason,
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
        if self.meta.object_type != "Checkpoint":
            raise ContractInvalid("meta.object_type must be Checkpoint")
        if self.meta.owner_organ != OWNER_MAP["Checkpoint"]:
            raise AuthorityViolation("Checkpoint owner_organ mismatch")
        if self.pending_actions:
            raise ContractInvalid("Checkpoint.pending_actions must be empty in E3")
        if self.ticket_refs:
            raise ContractInvalid("Checkpoint.ticket_refs must be empty in E3")

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
        meta_fields = {
            "schema_version": SCHEMA_VERSION,
            "object_type": "Checkpoint",
            "object_id": object_id,
            "revision": 1,
            "owner_organ": OWNER_MAP["Checkpoint"],
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
            object_type="Checkpoint",
            object_id=object_id,
            revision=1,
            owner_organ=OWNER_MAP["Checkpoint"],
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
        return Checkpoint(
            meta=meta,
            task_revision=task_revision,
            phase=phase,
            disposition=disposition,
            event_cursor=event_cursor,
            pending_requests=pending_requests,
            pending_actions=(),
            snapshot_ref=snapshot_ref,
            ticket_refs=(),
            reason=reason,
        )

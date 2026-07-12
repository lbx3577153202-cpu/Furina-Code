"""Furina Code — CLI entry point for inspect commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path

from .contracts.errors import FurinaContractError, IdempotencyConflict, ContractInvalid, GateNotSatisfied
from .contracts.meta import canonical_json_dumps, now_utc, compute_integrity_ref
from .contracts.objects import (
    RunBinding, TaskDossier, TaskRun, Checkpoint,
    BackendProfile, ContextEnvelope, CandidateEnvelope, ProjectSnapshot,
    EvidenceEnvelope, VerificationPlan, VerificationVerdict, CompletionVerdict,
    Phase, Disposition, RunBindingStatus, TaskDossierStatus,
)
from .ledger.sqlite import Ledger
from .world.snapshot import create_project_snapshot
from .readonly.context import create_context_envelope, write_context_packet
from .readonly.file_backend_bridge import prepare_e4_file_transport, finalize_e4_file_transport
from .backend.candidate import (
    validate_candidate_file,
    validate_candidate_content,
    read_candidate_once,
    create_candidate_envelope,
)
from .readonly.verification import (
    create_verification_plan,
    execute_verification,
    build_gate_results,
    evaluate_gate,
)
from .readonly.completion import create_completion_verdict


def _generate_ids() -> dict[str, str]:
    return {
        "run_binding_id": f"rb-{uuid.uuid4().hex[:12]}",
        "task_id": f"task-{uuid.uuid4().hex[:12]}",
        "task_run_id": f"tr-{uuid.uuid4().hex[:12]}",
        "correlation_id": f"corr-{uuid.uuid4().hex[:12]}",
        "project_ref": "furina-code",
    }


def _payload_from_obj(obj) -> dict:
    """Extract payload dict from any formal object."""
    t = obj.meta.object_type
    if t == "RunBinding":
        return {"subject_ref": obj.subject_ref, "user_ref": obj.user_ref,
                "project_ref": obj.project_ref, "task_ref": obj.task_ref,
                "allowed_tool_classes": list(obj.allowed_tool_classes),
                "status": obj.status.value, "source_refs": list(obj.source_refs)}
    if t == "TaskDossier":
        return {"source_intent_ref": obj.source_intent_ref,
                "structured_goal": obj.structured_goal,
                "success_criteria": list(obj.success_criteria),
                "scope": list(obj.scope), "exclusions": list(obj.exclusions),
                "unknowns": list(obj.unknowns), "risk_class": obj.risk_class,
                "user_constraints": list(obj.user_constraints), "status": obj.status.value}
    if t == "TaskRun":
        return {"task_revision": obj.task_revision,
                "phase": obj.phase.value, "disposition": obj.disposition.value,
                "current_refs": list(obj.current_refs),
                "open_requests": list(obj.open_requests),
                "started_at": obj.started_at.isoformat(),
                "terminal_reason": obj.terminal_reason}
    if t == "Checkpoint":
        return {"task_revision": obj.task_revision,
                "phase": obj.phase.value, "disposition": obj.disposition.value,
                "event_cursor": obj.event_cursor,
                "pending_requests": list(obj.pending_requests),
                "pending_actions": list(obj.pending_actions),
                "snapshot_ref": obj.snapshot_ref,
                "ticket_refs": list(obj.ticket_refs), "reason": obj.reason}
    if t == "BackendProfile":
        return {"provider_ref": obj.provider_ref,
                "capabilities": list(obj.capabilities), "limits": obj.limits,
                "health": obj.health, "credential_mode": obj.credential_mode,
                "data_policy_ref": obj.data_policy_ref,
                "last_checked_at": obj.last_checked_at.isoformat(),
                "backend_id": obj.backend_id, "backend_kind": obj.backend_kind}
    if t == "ContextEnvelope":
        return {"task_revision": obj.task_revision, "purpose": obj.purpose,
                "snapshot_ref": obj.snapshot_ref, "task_dossier_ref": obj.task_dossier_ref,
                "included_refs": list(obj.included_refs), "redactions": list(obj.redactions),
                "classification_summary": obj.classification_summary,
                "disclosure_basis": obj.disclosure_basis, "backend_ref": obj.backend_ref,
                "instruction_profile": obj.instruction_profile, "context_digest": obj.context_digest,
                "context_payload": obj.context_payload}
    if t == "CandidateEnvelope":
        return {"candidate_type": obj.candidate_type,
                "backend_profile_ref": obj.backend_profile_ref,
                "backend_session_ref": obj.backend_session_ref,
                "context_ref": obj.context_ref, "content_ref": obj.content_ref,
                "candidate_digest": obj.candidate_digest,
                "claimed_assumptions": list(obj.claimed_assumptions),
                "requested_actions": list(obj.requested_actions),
                "received_at": obj.received_at.isoformat(), "status": obj.status}
    if t == "ProjectSnapshot":
        return {"observation_scope": obj.observation_scope, "git_ref": obj.git_ref,
                "file_facts": obj.file_facts, "environment_facts": obj.environment_facts,
                "blind_spots": list(obj.blind_spots), "observed_at": obj.observed_at.isoformat(),
                "freshness_policy": obj.freshness_policy,
                "head_sha": obj.head_sha, "branch": obj.branch,
                "status_lines": list(obj.status_lines),
                "tracked_count": obj.tracked_count, "untracked_count": obj.untracked_count,
                "is_clean": obj.is_clean, "pyproject_exists": obj.pyproject_exists,
                "pyproject_sha256": obj.pyproject_sha256, "requires_python": obj.requires_python,
                "runtime_deps": list(obj.runtime_deps), "dev_deps": list(obj.dev_deps),
                "pytest_testpaths": list(obj.pytest_testpaths),
                "ci_config_exists": obj.ci_config_exists, "ci_config_sha256": obj.ci_config_sha256,
                "snapshot_sha256": obj.snapshot_sha256}
    if t == "EvidenceEnvelope":
        return {"claim_scope": obj.claim_scope, "evidence_type": obj.evidence_type,
                "source_ref": obj.source_ref, "claim": obj.claim,
                "source_refs": list(obj.source_refs), "causal_links": list(obj.causal_links),
                "supporting_refs": list(obj.supporting_refs),
                "integrity_status": obj.integrity_status, "redactions": list(obj.redactions),
                "retention_class": obj.retention_class, "missing_evidence": list(obj.missing_evidence)}
    if t == "VerificationPlan":
        return {"task_revision": obj.task_revision, "candidate_ref": obj.candidate_ref,
                "success_criteria_map": obj.success_criteria_map,
                "success_criteria": list(obj.success_criteria), "checks": list(obj.checks),
                "required_evidence": list(obj.required_evidence),
                "independence_requirements": list(obj.independence_requirements),
                "stop_conditions": list(obj.stop_conditions), "steps": list(obj.steps)}
    if t == "VerificationVerdict":
        return {"plan_ref": obj.plan_ref, "evidence_refs": list(obj.evidence_refs),
                "criterion_results": obj.criterion_results, "coverage": obj.coverage,
                "failed_checks": list(obj.failed_checks), "unknowns": list(obj.unknowns),
                "outcome": obj.outcome, "reason": obj.reason, "checked_at": obj.checked_at.isoformat()}
    if t == "CompletionVerdict":
        return {"task_revision": obj.task_revision, "task_run_ref": obj.task_run_ref,
                "verification_ref": obj.verification_ref,
                "reconciliation_refs": list(obj.reconciliation_refs),
                "candidate_ref": obj.candidate_ref, "outcome": obj.outcome,
                "completed_items": list(obj.completed_items),
                "incomplete_items": list(obj.incomplete_items),
                "unverified_items": list(obj.unverified_items),
                "residual_risks": list(obj.residual_risks),
                "no_project_side_effect": obj.no_project_side_effect, "user_effect": obj.user_effect}
    raise ValueError(f"Unknown object type: {t}")


def _write_obj(ledger: Ledger, obj, caller_organ: str, expected_revision: int) -> None:
    ledger.write_object(obj.meta, _payload_from_obj(obj), caller_organ, expected_revision)


def _validate_raw_path(path: str, label: str) -> None:
    """Reject raw CLI path arguments containing traversal before any resolve."""
    if ".." in Path(path).parts:
        raise ContractInvalid(f"Path traversal rejected: {path}")


def _validate_workspace_path(workspace: str) -> None:
    """Reject paths that aren't inside a git repo.

    Uses observe_git to resolve the real repository root, which allows
    subdirectories of a git repo to be valid workspace paths.
    """
    from .world.git import observe_git
    try:
        observe_git(workspace)
    except Exception:
        raise ContractInvalid(f"Not a git repository: {workspace}")


def _validate_runtime_not_in_workspace(workspace: str, runtime_dir: str) -> None:
    """Reject runtime-dir inside the canonical repository root.

    Uses observe_git to resolve the real repository root, so a workspace
    like repo/tests/e4 correctly rejects repo/.furina-runtime.
    """
    from .world.git import observe_git
    try:
        git_obs = observe_git(workspace)
        repo_root = Path(git_obs["repository_root"]).resolve()
    except Exception:
        repo_root = Path(workspace).resolve()
    rt = Path(runtime_dir).resolve()
    try:
        rt.relative_to(repo_root)
        raise ContractInvalid("runtime-dir must not be inside repository root")
    except ValueError:
        pass  # rt is not inside repo_root — good


def cmd_prepare(args: argparse.Namespace) -> int:
    """Execute the prepare command."""
    # Validate raw paths BEFORE resolve
    try:
        _validate_raw_path(args.workspace, "workspace")
        _validate_raw_path(args.runtime_dir, "runtime_dir")
    except FurinaContractError as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}), file=sys.stderr)
        return 1

    workspace = str(Path(args.workspace).resolve())
    runtime_dir = Path(args.runtime_dir).resolve()

    try:
        _validate_workspace_path(workspace)
        _validate_runtime_not_in_workspace(workspace, str(runtime_dir))
        from .world.git import resolve_repository_root
        repository_root = Path(resolve_repository_root(workspace)).resolve()
    except FurinaContractError as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}), file=sys.stderr)
        return 1

    runtime_dir.mkdir(parents=True, exist_ok=True)

    ids = _generate_ids()
    db_path = str(runtime_dir / "inspect.sqlite3")

    try:
        ledger = Ledger(db_path)
        ledger.open()

        rb_id = ids["run_binding_id"]
        task_id = ids["task_id"]
        tr_id = ids["task_run_id"]
        proj = ids["project_ref"]
        corr = ids["correlation_id"]

        # 1. RunBinding
        rb = RunBinding.create(
            run_binding_id=rb_id, task_id=task_id, task_run_id=tr_id,
            project_ref=proj, correlation_id=corr,
            subject_ref="cli", user_ref="cli", task_ref=task_id,
            allowed_tool_classes=("git_read",), source_refs=(),
        )
        _write_obj(ledger, rb, "I1-A", 0)

        # 2. TaskDossier with full 10 success criteria
        td = TaskDossier.create(
            run_binding_id=rb_id, task_id=task_id, task_run_id=tr_id,
            project_ref=proj, correlation_id=corr,
            source_intent_ref="cli:inspect",
            structured_goal="Generate repository baseline report",
            success_criteria=(
                "HEAD observed",
                "branch observed",
                "working tree status",
                "file counts correct",
                "Python version cataloged",
                "runtime deps cataloged",
                "dev deps cataloged",
                "pytest testpaths cataloged",
                "CI config cataloged",
                "blind spots recorded",
            ),
            scope=("repository metadata",),
            exclusions=("source code analysis", "code quality", "security audit"),
            unknowns=(),
            risk_class="low",
            user_constraints=("read-only",),
            causation_ref=rb.meta.integrity_ref,
        )
        _write_obj(ledger, td, "I2-A", 0)

        # 3. BackendProfile
        bp = BackendProfile.create(
            run_binding_id=rb_id, task_id=task_id, task_run_id=tr_id,
            project_ref=proj, correlation_id=corr,
            provider_ref="local-cli",
            capabilities=("git_read", "file_read"),
            limits={"max_candidate_bytes": 10_000_000},
            health="available", credential_mode="none",
            data_policy_ref="local-only",
            backend_id="local-cli", backend_kind="local",
            causation_ref=rb.meta.integrity_ref,
        )
        _write_obj(ledger, bp, "I2-B", 0)

        # 4. TaskRun at intake/active — causation_ref = TaskDossier
        tr = TaskRun.create(
            run_binding_id=rb_id, task_id=task_id, task_run_id=tr_id,
            project_ref=proj, correlation_id=corr, task_revision=1,
            causation_ref=td.meta.integrity_ref,
        )
        _write_obj(ledger, tr, "I2-D", 0)

        # 5. intake/active → observe/active (supersedes chain from E3)
        tr = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        _write_obj(ledger, tr, "I2-D", 1)

        # 6. ProjectSnapshot — causation_ref = observe/active TaskRun revision
        snapshot = create_project_snapshot(
            run_binding_id=rb_id, task_id=task_id, task_run_id=tr_id,
            project_ref=proj, correlation_id=corr,
            workspace=workspace,
            causation_ref=tr.meta.integrity_ref,
        )
        _write_obj(ledger, snapshot, "I3-A", 0)

        # 7. observe/active → deliberate/active
        tr = tr.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE)
        _write_obj(ledger, tr, "I2-D", 2)

        # 8. ContextEnvelope
        ctx = create_context_envelope(
            run_binding_id=rb_id, task_id=task_id, task_run_id=tr_id,
            project_ref=proj, correlation_id=corr,
            snapshot=snapshot, dossier=td,
            backend_ref=bp.meta.integrity_ref,
            causation_ref=snapshot.meta.integrity_ref,
        )
        _write_obj(ledger, ctx, "I2-C", 0)

        # 9. deliberate/active → deliberate/external_blocked
        tr = tr.transition("I2-D", Phase.DELIBERATE, Disposition.EXTERNAL_BLOCKED,
                           current_refs=(snapshot.meta.integrity_ref, ctx.meta.integrity_ref))
        _write_obj(ledger, tr, "I2-D", 3)

        # 10. Checkpoint — causation_ref points to the deliberate/external_blocked TaskRun
        cp = Checkpoint.create(
            run_binding_id=rb_id, task_id=task_id, task_run_id=tr_id,
            project_ref=proj, correlation_id=corr,
            task_revision=1, phase=Phase.DELIBERATE,
            disposition=Disposition.EXTERNAL_BLOCKED,
            event_cursor=ledger.get_last_sequence(rb_id),
            pending_requests=("candidate_file",),
            snapshot_ref=snapshot.meta.integrity_ref,
            reason="prepare complete — awaiting external candidate",
            causation_ref=tr.meta.integrity_ref,
        )
        _write_obj(ledger, cp, "I1-C", 0)

        ledger.close()

        # Write context packet
        ctx_path = str(runtime_dir / "context_packet.json")
        ctx_digest = write_context_packet(ctx, ctx_path)

        # Wire to FileBackend — probe, prepare, invoke
        request_sandbox_ref = f"backend/{rb_id}/{tr_id}"
        try:
            transport, candidate_drop_path = prepare_e4_file_transport(
                runtime_dir=runtime_dir,
                repository_root=repository_root,
                run_binding_id=rb_id,
                task_run_id=tr_id,
                backend_profile_ref=bp.meta.integrity_ref,
                context_ref=ctx.meta.integrity_ref,
                context_digest=ctx_digest,
                instruction_profile=ctx.instruction_profile,
                max_candidate_bytes=bp.limits.get("max_candidate_bytes", 10_000_000),
            )
        except ContractInvalid as fb_exc:
            print(json.dumps({
                "error": fb_exc.code,
                "message": fb_exc.message,
            }), file=sys.stderr)
            return 1

        output = {
            "run_binding_id": rb_id,
            "task_id": task_id,
            "task_run_id": tr_id,
            "project_snapshot_ref": snapshot.meta.integrity_ref,
            "backend_profile_ref": bp.meta.integrity_ref,
            "context_envelope_ref": ctx.meta.integrity_ref,
            "context_packet_path": ctx_path,
            "context_digest": ctx_digest,
            "status": "AWAITING_EXTERNAL_CANDIDATE",
            "backend_transport_status": transport.transport_status,
            "backend_sandbox_ref": request_sandbox_ref,
            "candidate_drop_path": candidate_drop_path,
        }
        print(canonical_json_dumps(output))
        return 0

    except FurinaContractError as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}), file=sys.stderr)
        return 1
    except Exception as exc:
        print(json.dumps({"error": "INTERNAL_ERROR", "message": str(exc)}), file=sys.stderr)
        return 3


def _load_latest_object(ledger: Ledger, rb_id: str, object_type: str):
    """Load the latest revision of an object type from verified events."""
    events = ledger.get_verified_events(rb_id)
    type_events = [e for e in events if e["event_type"].startswith(f"{object_type}.")]
    if not type_events:
        return None, None, None
    agg_ref = type_events[-1]["aggregate_ref"]
    obj_id = agg_ref.split(":", 1)[1] if ":" in agg_ref else agg_ref
    result = ledger.get_latest(object_type, obj_id)
    if result is None:
        return None, None, None
    meta, payload = result
    return meta, payload, events


def cmd_finalize(args: argparse.Namespace) -> int:
    """Execute the finalize command."""
    # Validate raw paths BEFORE resolve
    try:
        _validate_raw_path(args.runtime_dir, "runtime_dir")
        _validate_raw_path(args.candidate_file, "candidate_file")
    except FurinaContractError as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}), file=sys.stderr)
        return 1

    runtime_dir = Path(args.runtime_dir).resolve()
    db_path = str(runtime_dir / "inspect.sqlite3")

    if not Path(db_path).exists():
        print(json.dumps({"error": "NO_LEDGER", "message": f"No ledger found at {db_path}"}), file=sys.stderr)
        return 2

    try:
        ledger = Ledger(db_path)
        ledger.open()

        rb_id = args.run_binding_id
        candidate_path = args.candidate_file

        # Load TaskRun
        tr_meta, tr_payload, tr_events = _load_latest_object(ledger, rb_id, "TaskRun")
        if tr_meta is None:
            print(json.dumps({"error": "NO_TASK_RUN", "message": "No TaskRun found"}), file=sys.stderr)
            return 1

        # Idempotency check deferred — requires FileBackend canonical digest

        # Must be in deliberate/external_blocked (or terminal for idempotency)
        is_terminal = (tr_payload["phase"] == "terminal"
                       and tr_payload["disposition"] == "terminal")
        if not is_terminal and (tr_payload["phase"] != "deliberate"
                                or tr_payload["disposition"] != "external_blocked"):
            print(json.dumps({
                "error": "WRONG_PHASE",
                "message": f"TaskRun is {tr_payload['phase']}/{tr_payload['disposition']}, "
                           f"expected deliberate/external_blocked or terminal/terminal",
            }), file=sys.stderr)
            return 1

        # Load ContextEnvelope
        ctx_meta, ctx_payload, _ = _load_latest_object(ledger, rb_id, "ContextEnvelope")
        if ctx_meta is None:
            print(json.dumps({"error": "NO_CONTEXT", "message": "No ContextEnvelope found"}), file=sys.stderr)
            return 1

        # Load BackendProfile
        bp_meta, bp_payload, _ = _load_latest_object(ledger, rb_id, "BackendProfile")

        # Load ProjectSnapshot
        snap_meta, snap_payload, _ = _load_latest_object(ledger, rb_id, "ProjectSnapshot")
        if snap_meta is None:
            print(json.dumps({"error": "NO_SNAPSHOT", "message": "No ProjectSnapshot found"}), file=sys.stderr)
            return 1

        # Reconstruct ProjectSnapshot
        snapshot = ProjectSnapshot(
            meta=snap_meta,
            observation_scope=snap_payload.get("observation_scope", ""),
            git_ref=snap_payload.get("git_ref", {}),
            file_facts=snap_payload.get("file_facts", {}),
            environment_facts=snap_payload.get("environment_facts", {}),
            blind_spots=tuple(snap_payload.get("blind_spots", [])),
            observed_at=snap_meta.created_at,
            freshness_policy=snap_payload.get("freshness_policy", "point-in-time"),
            head_sha=snap_payload["head_sha"], branch=snap_payload["branch"],
            status_lines=tuple(snap_payload["status_lines"]),
            tracked_count=snap_payload["tracked_count"],
            untracked_count=snap_payload["untracked_count"],
            is_clean=snap_payload["is_clean"],
            pyproject_exists=snap_payload["pyproject_exists"],
            pyproject_sha256=snap_payload.get("pyproject_sha256"),
            requires_python=snap_payload.get("requires_python"),
            runtime_deps=tuple(snap_payload.get("runtime_deps", [])),
            dev_deps=tuple(snap_payload.get("dev_deps", [])),
            pytest_testpaths=tuple(snap_payload.get("pytest_testpaths", [])),
            ci_config_exists=snap_payload.get("ci_config_exists", False),
            ci_config_sha256=snap_payload.get("ci_config_sha256"),
            snapshot_sha256=snap_payload["snapshot_sha256"],
        )

        # Read context packet and verify digest
        ctx_packet_path = runtime_dir / "context_packet.json"
        if not ctx_packet_path.exists():
            print(json.dumps({"error": "NO_CONTEXT_PACKET", "message": "Context packet file not found"}), file=sys.stderr)
            return 1
        ctx_packet = json.loads(ctx_packet_path.read_text(encoding="utf-8"))
        # Recompute digest from the same structure used during creation
        digest_input = {
            "schema_version": ctx_packet.get("schema_version", "1.0"),
            "snapshot_ref": ctx_packet.get("snapshot_ref"),
            "task_dossier_ref": ctx_packet.get("task_dossier_ref"),
            "context_payload": ctx_packet.get("context_payload"),
            "instruction_profile": ctx_packet.get("instruction_profile"),
        }
        computed_ctx_digest = "sha256:" + hashlib.sha256(
            canonical_json_dumps(digest_input).encode("utf-8")
        ).hexdigest()
        if computed_ctx_digest != ctx_payload.get("context_digest"):
            print(json.dumps({"error": "CONTEXT_DIGEST_MISMATCH",
                              "message": "Context packet digest does not match ContextEnvelope"}), file=sys.stderr)
            return 1

        # Resolve repository root for FileBackend forbidden_roots
        # ProjectSnapshot git_ref does not store repository_root.
        # The runtime_dir was already validated to be outside the repository
        # during prepare. For finalize, FileBackend only reads within runtime_dir.
        repository_root = None  # not available from ledger; use empty forbidden_roots

        # FileBackend lifecycle: prepare → invoke → collect → strict_validate
        instruction_profile = ctx_packet.get("instruction_profile", {"id": "e4-repository-baseline-v1", "version": "1.0"})
        try:
            transport = finalize_e4_file_transport(
                runtime_dir=runtime_dir,
                repository_root=repository_root,
                run_binding_id=rb_id,
                task_run_id=tr_meta.task_run_id,
                candidate_file=candidate_path,
                backend_profile_ref=bp_meta.integrity_ref if bp_meta else "e4-repository-baseline-v1",
                context_ref=ctx_meta.integrity_ref,
                context_digest=ctx_payload.get("context_digest", ""),
                instruction_profile=instruction_profile,
                max_candidate_bytes=bp_payload.get("limits", {}).get("max_candidate_bytes", 10_000_000) if bp_payload else 10_000_000,
            )
        except ContractInvalid as fb_exc:
            # On terminal runs, collect/validation failure with different
            # candidate maps to IDEMPOTENCY_CONFLICT
            if is_terminal and fb_exc.message in (
                "FILE_BACKEND_COLLECT_FAILED",
                "FILE_BACKEND_VALIDATION_FAILED",
                "FILE_BACKEND_INVOKE_FAILED",
                "CANDIDATE_NOT_FOUND",
            ):
                print(json.dumps({
                    "error": "IDEMPOTENCY_CONFLICT",
                    "message": "Different candidate submitted for completed run",
                }), file=sys.stderr)
                ledger.close()
                return 1
            print(json.dumps({
                "error": fb_exc.code,
                "message": fb_exc.message,
            }), file=sys.stderr)
            return 1

        # Read canonical collected candidate artifact (frozen evidence)
        # The canonical artifact path is deterministic from sandbox_path_ref
        canonical_artifact_path = runtime_dir / transport.candidate_ref
        cand_text, cand_parsed, cand_raw_hex = read_candidate_once(
            str(canonical_artifact_path)
        )
        cand_digest = f"sha256:{cand_raw_hex}"

        if cand_digest != transport.candidate_digest:
            print(json.dumps({
                "error": "CANDIDATE_EVIDENCE_MISMATCH",
                "message": "Canonical artifact digest does not match transport digest",
            }), file=sys.stderr)
            return 1

        # Idempotency check using FileBackend canonical digest
        if is_terminal:
            cv_meta, cv_payload, _ = _load_latest_object(ledger, rb_id, "CompletionVerdict")
            if cv_meta is not None:
                ce_meta, ce_payload, _ = _load_latest_object(ledger, rb_id, "CandidateEnvelope")
                if ce_meta is not None and ce_payload.get("candidate_digest") == cand_digest:
                    # Same candidate replay — return complete core result from Ledger
                    vp_meta, _, _ = _load_latest_object(ledger, rb_id, "VerificationPlan")
                    vv_meta, _, _ = _load_latest_object(ledger, rb_id, "VerificationVerdict")
                    tr_head_meta, _, _ = _load_latest_object(ledger, rb_id, "TaskRun")
                    print(canonical_json_dumps({
                        "candidate_ref": ce_meta.integrity_ref,
                        "verification_plan_ref": vp_meta.integrity_ref if vp_meta else None,
                        "verification_verdict_ref": vv_meta.integrity_ref if vv_meta else None,
                        "completion_verdict_ref": cv_meta.integrity_ref,
                        "task_run_ref": tr_head_meta.integrity_ref if tr_head_meta else None,
                        "outcome": cv_payload["outcome"],
                        "completed_items": cv_payload.get("completed_items", []),
                        "incomplete_items": cv_payload.get("incomplete_items", []),
                        "unverified_items": cv_payload.get("unverified_items", []),
                        "residual_risks": cv_payload.get("residual_risks", []),
                        "user_effect": cv_payload.get("user_effect", ""),
                    }))
                    ledger.close()
                    return 0
                else:
                    print(json.dumps({"error": "IDEMPOTENCY_CONFLICT",
                                      "message": "Different candidate submitted for completed run"}), file=sys.stderr)
                    ledger.close()
                    return 1

        # Create CandidateEnvelope (only after FileBackend validation passes)
        ce = create_candidate_envelope(
            run_binding_id=rb_id,
            task_id=tr_meta.task_id, task_run_id=tr_meta.task_run_id,
            project_ref=tr_meta.project_ref, correlation_id=tr_meta.correlation_id,
            candidate_type=cand_parsed.get("candidate_type", "repository_baseline_report"),
            backend_profile_ref=bp_meta.integrity_ref if bp_meta else "e4-repository-baseline-v1",
            backend_session_ref=cand_parsed.get("backend_session_ref", "unknown"),
            context_ref=ctx_meta.integrity_ref,
            content_ref=compute_integrity_ref({}, cand_parsed.get("content", {})),
            candidate_digest=cand_digest,
            claimed_assumptions=tuple(cand_parsed.get("claimed_assumptions", [])),
            requested_actions=tuple(cand_parsed.get("requested_actions", [])),
            causation_ref=ctx_meta.integrity_ref,
        )
        _write_obj(ledger, ce, "I2-D", 0)

        # Transition: external_blocked → active
        new_tr = TaskRun(
            meta=tr_meta, task_revision=tr_payload["task_revision"],
            phase=Phase.DELIBERATE, disposition=Disposition.EXTERNAL_BLOCKED,
            current_refs=tuple(tr_payload.get("current_refs", [])),
            open_requests=tuple(tr_payload.get("open_requests", [])),
            started_at=tr_meta.created_at,
            terminal_reason=tr_payload.get("terminal_reason"),
        )
        new_tr = new_tr.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE,
                                   current_refs=(ce.meta.integrity_ref,))
        _write_obj(ledger, new_tr, "I2-D", tr_meta.revision)

        # deliberate/active → verify/active
        new_tr = new_tr.transition("I2-D", Phase.VERIFY, Disposition.ACTIVE)
        _write_obj(ledger, new_tr, "I2-D", new_tr.meta.revision - 1)

        # VerificationPlan — build from TaskDossier success_criteria
        from .readonly.verification import CRITERIA_MAP
        td_meta_loaded, td_payload_loaded, _ = _load_latest_object(ledger, rb_id, "TaskDossier")
        td_criteria = tuple(td_payload_loaded.get("success_criteria", [])) if td_payload_loaded else tuple(CRITERIA_MAP.keys())
        # Build criteria_map from dossier criteria using CRITERIA_MAP as registry
        criteria_map = {}
        checks_list = []
        for crit in td_criteria:
            check = CRITERIA_MAP.get(crit, crit)
            criteria_map[crit] = check
            checks_list.append(check)
        required_ev = tuple(f"evidence:{c}" for c in checks_list)
        vplan = create_verification_plan(
            run_binding_id=rb_id,
            task_id=tr_meta.task_id, task_run_id=tr_meta.task_run_id,
            project_ref=tr_meta.project_ref, correlation_id=tr_meta.correlation_id,
            task_revision=tr_payload["task_revision"],
            candidate_ref=ce.meta.integrity_ref,
            success_criteria_map=criteria_map,
            success_criteria=td_criteria,
            checks=tuple(checks_list),
            required_evidence=required_ev,
            independence_requirements=("local deterministic verification",),
            stop_conditions=("any_critical_check_fails",),
            causation_ref=ce.meta.integrity_ref,
        )
        _write_obj(ledger, vplan, "I4-D", 0)

        # Execute verification
        evidences, per_step_verdicts, agg_verdict = execute_verification(
            run_binding_id=rb_id,
            task_id=tr_meta.task_id, task_run_id=tr_meta.task_run_id,
            project_ref=tr_meta.project_ref, correlation_id=tr_meta.correlation_id,
            plan=vplan, candidate_content=cand_parsed, snapshot=snapshot,
            backend_profile_ref=bp_meta.integrity_ref if bp_meta else "",
            context_envelope_ref=ctx_meta.integrity_ref,
            candidate_envelope_ref=ce.meta.integrity_ref,
        )
        for ev in evidences:
            _write_obj(ledger, ev, "I4-C", 0)
        _write_obj(ledger, agg_verdict, "I4-D", 0)

        # Load real objects for gate evaluation
        from .contracts.objects import RunBinding as RB, TaskDossier as TD, BackendProfile as BPObj, ContextEnvelope as CtxObj
        rb_obj = None
        td_obj = None
        bp_obj = None
        ctx_obj = None
        rb_meta_loaded, rb_payload_loaded, _ = _load_latest_object(ledger, rb_id, "RunBinding")
        if rb_meta_loaded:
            rb_obj = RB(
                meta=rb_meta_loaded,
                subject_ref=rb_payload_loaded.get("subject_ref", ""),
                user_ref=rb_payload_loaded.get("user_ref", ""),
                project_ref=rb_payload_loaded.get("project_ref", ""),
                task_ref=rb_payload_loaded.get("task_ref", ""),
                allowed_tool_classes=tuple(rb_payload_loaded.get("allowed_tool_classes", [])),
                status=RunBindingStatus(rb_payload_loaded.get("status", "active")),
                source_refs=tuple(rb_payload_loaded.get("source_refs", [])),
            )
        if td_meta_loaded:
            td_obj = TD(
                meta=td_meta_loaded,
                source_intent_ref=td_payload_loaded.get("source_intent_ref", ""),
                structured_goal=td_payload_loaded.get("structured_goal", ""),
                success_criteria=tuple(td_payload_loaded.get("success_criteria", [])),
                scope=tuple(td_payload_loaded.get("scope", [])),
                exclusions=tuple(td_payload_loaded.get("exclusions", [])),
                unknowns=tuple(td_payload_loaded.get("unknowns", [])),
                risk_class=td_payload_loaded.get("risk_class", ""),
                user_constraints=tuple(td_payload_loaded.get("user_constraints", [])),
                status=TaskDossierStatus(td_payload_loaded.get("status", "active")),
            )
        if bp_meta and bp_payload:
            bp_obj = BPObj(
                meta=bp_meta,
                provider_ref=bp_payload.get("provider_ref", ""),
                capabilities=tuple(bp_payload.get("capabilities", [])),
                limits=bp_payload.get("limits", {}),
                health=bp_payload.get("health", ""),
                credential_mode=bp_payload.get("credential_mode", ""),
                data_policy_ref=bp_payload.get("data_policy_ref", ""),
                last_checked_at=bp_meta.created_at,
                backend_id=bp_payload.get("backend_id", ""),
                backend_kind=bp_payload.get("backend_kind", ""),
            )
        if ctx_meta and ctx_payload:
            ctx_obj = CtxObj(
                meta=ctx_meta,
                task_revision=ctx_payload.get("task_revision", 1),
                purpose=ctx_payload.get("purpose", ""),
                snapshot_ref=ctx_payload.get("snapshot_ref", ""),
                task_dossier_ref=ctx_payload.get("task_dossier_ref", ""),
                included_refs=tuple(ctx_payload.get("included_refs", [])),
                redactions=tuple(ctx_payload.get("redactions", [])),
                classification_summary=ctx_payload.get("classification_summary", ""),
                disclosure_basis=ctx_payload.get("disclosure_basis", ""),
                backend_ref=ctx_payload.get("backend_ref", ""),
                instruction_profile=ctx_payload.get("instruction_profile", {}),
                context_digest=ctx_payload.get("context_digest", ""),
                context_payload=ctx_payload.get("context_payload", {}),
            )

        # verify/active → adjudicate/active
        new_tr = new_tr.transition("I2-D", Phase.ADJUDICATE, Disposition.ACTIVE)
        _write_obj(ledger, new_tr, "I2-D", new_tr.meta.revision - 1)

        # --- Phase 1: Pre-completion gates (G0/G1/G2/G4/G6) ---
        pre_gate_ids = ("IL-G0", "IL-G1", "IL-G2", "IL-G4", "IL-G6")
        pre_gate_evidences: list = []
        pre_gate_results: list = []
        pre_gates_all_pass = True
        for gid in pre_gate_ids:
            gr = evaluate_gate(gid, rb_obj, td_obj, snapshot, bp_obj, ctx_obj,
                               ce, vplan, agg_verdict, None, task_run=new_tr,
                               verification_evidence=evidences if gid == "IL-G6" else None)
            pre_gate_results.append(gr)
            if gr.outcome != "pass":
                pre_gates_all_pass = False
            # Build evidence for pre-gate
            ev = EvidenceEnvelope.create(
                run_binding_id=rb_id,
                task_id=tr_meta.task_id, task_run_id=tr_meta.task_run_id,
                project_ref=tr_meta.project_ref, correlation_id=tr_meta.correlation_id,
                claim_scope=gid, evidence_type="gate_evaluation",
                source_ref=f"gate:{gid}",
                claim=f"{gid}: {gr.outcome}",
                source_refs=gr.supporting_refs,
                supporting_refs=tuple(
                    obj.meta.integrity_ref for obj in [rb_obj, td_obj, snapshot, bp_obj, ctx_obj, ce, vplan, agg_verdict, new_tr]
                    if obj is not None and hasattr(obj, 'meta')
                ),
                integrity_status="verified" if gr.outcome == "pass" else "failed",
                envelope_id=f"{tr_meta.task_id}:gate:{gid}",
                causation_ref=agg_verdict.meta.integrity_ref if agg_verdict else None,
            )
            gr.evidence_ref = ev.meta.integrity_ref
            pre_gate_evidences.append(ev)

        # --- CompletionVerdict: outcome depends on pre-gates + verification ---
        verification_passed = agg_verdict.outcome == "pass"
        if verification_passed and pre_gates_all_pass:
            cv_outcome = "completed"
        elif not verification_passed:
            cv_outcome = "not_completed"
        else:
            cv_outcome = "manual_decision_required"

        cv = create_completion_verdict(
            run_binding_id=rb_id,
            task_id=tr_meta.task_id, task_run_id=tr_meta.task_run_id,
            project_ref=tr_meta.project_ref, correlation_id=tr_meta.correlation_id,
            task_revision=tr_payload["task_revision"],
            task_run_ref=new_tr.meta.integrity_ref,
            verification_ref=agg_verdict.meta.integrity_ref,
            candidate_ref=ce.meta.integrity_ref,
            outcome=cv_outcome,
            completed_items=tuple(k for k, v in agg_verdict.criterion_results.items() if v == "pass"),
            incomplete_items=tuple(agg_verdict.failed_checks),
            unverified_items=tuple(agg_verdict.unknowns),
            residual_risks=tuple(
                list(agg_verdict.failed_checks) +
                [gr.gate_id for gr in pre_gate_results if gr.outcome != "pass"]
            ) if (agg_verdict.failed_checks or not pre_gates_all_pass) else (),
            no_project_side_effect=True,
            user_effect="No project files modified. No project tests run. Project code correctness not verified. Authorization Gate not implemented. Controlled write not implemented. RecoveryVerdict not implemented. No experience formed.",
            causation_ref=agg_verdict.meta.integrity_ref,
        )
        _write_obj(ledger, cv, "I4-E", 0)

        # Write pre-gate evidences
        for ev in pre_gate_evidences:
            _write_obj(ledger, ev, "I4-C", 0)

        # --- Phase 2: Post-completion gate (IL-G7) ---
        # Read current heads from Ledger for head verification
        _cv_head_meta, _, _ = _load_latest_object(ledger, rb_id, "CompletionVerdict")
        _vv_head_meta, _, _ = _load_latest_object(ledger, rb_id, "VerificationVerdict")
        _tr_head_meta, _, _ = _load_latest_object(ledger, rb_id, "TaskRun")
        current_heads = {}
        if _cv_head_meta:
            current_heads["CompletionVerdict"] = _cv_head_meta.integrity_ref
        if _vv_head_meta:
            current_heads["VerificationVerdict"] = _vv_head_meta.integrity_ref
        if _tr_head_meta:
            current_heads["TaskRun"] = _tr_head_meta.integrity_ref

        g7_result = evaluate_gate("IL-G7", rb_obj, td_obj, snapshot, bp_obj, ctx_obj,
                                  ce, vplan, agg_verdict, cv, task_run=new_tr,
                                  current_heads=current_heads)
        g7_ev = EvidenceEnvelope.create(
            run_binding_id=rb_id,
            task_id=tr_meta.task_id, task_run_id=tr_meta.task_run_id,
            project_ref=tr_meta.project_ref, correlation_id=tr_meta.correlation_id,
            claim_scope="IL-G7", evidence_type="gate_evaluation",
            source_ref="gate:IL-G7",
            claim=f"IL-G7: {g7_result.outcome}",
            source_refs=g7_result.supporting_refs,
            supporting_refs=tuple(
                obj.meta.integrity_ref for obj in [cv, agg_verdict, new_tr]
                if obj is not None and hasattr(obj, 'meta')
            ),
            integrity_status="verified" if g7_result.outcome == "pass" else "failed",
            envelope_id=f"{tr_meta.task_id}:gate:IL-G7",
            causation_ref=cv.meta.integrity_ref,
        )
        g7_result.evidence_ref = g7_ev.meta.integrity_ref
        _write_obj(ledger, g7_ev, "I4-C", 0)

        all_gate_results = pre_gate_results + [g7_result]

        # --- G7 failure blocks terminal ---
        if g7_result.outcome != "pass":
            # TaskRun → adjudicate/paused (not terminal)
            new_tr = new_tr.transition("I2-D", Phase.ADJUDICATE, Disposition.PAUSED)
            _write_obj(ledger, new_tr, "I2-D", new_tr.meta.revision - 1)

            # Non-terminal checkpoint
            cp = Checkpoint.create(
                run_binding_id=rb_id,
                task_id=tr_meta.task_id, task_run_id=tr_meta.task_run_id,
                project_ref=tr_meta.project_ref, correlation_id=tr_meta.correlation_id,
                task_revision=2, phase=Phase.ADJUDICATE, disposition=Disposition.PAUSED,
                event_cursor=ledger.get_last_sequence(rb_id),
                pending_requests=(),
                snapshot_ref=snapshot.meta.integrity_ref,
                reason=f"G7 not satisfied — blocked terminal: {', '.join(g7_result.failed_conditions)}",
                causation_ref=cv.meta.integrity_ref,
            )
            _write_obj(ledger, cp, "I1-C", 0)
            ledger.close()

            # Output with error
            gate_summary = {}
            for gr in all_gate_results:
                gate_summary[gr.gate_id] = {
                    "gate_id": gr.gate_id, "outcome": gr.outcome,
                    "checked_conditions": list(gr.checked_conditions),
                    "supporting_refs": list(gr.supporting_refs),
                    "failed_conditions": list(gr.failed_conditions),
                    "checked_at": gr.checked_at, "evidence_ref": gr.evidence_ref,
                }
            output = {
                "error": "GATE_NOT_SATISFIED",
                "message": f"IL-G7 failed: {', '.join(g7_result.failed_conditions)}",
                "gate_results": gate_summary,
            }
            print(json.dumps(output), file=sys.stderr)
            return 1

        # --- G7 pass: proceed to terminal ---
        new_tr = new_tr.transition("I2-D", Phase.TERMINAL, Disposition.TERMINAL,
                                   terminal_reason=cv.outcome)
        _write_obj(ledger, new_tr, "I2-D", new_tr.meta.revision - 1)

        # Final checkpoint
        cp = Checkpoint.create(
            run_binding_id=rb_id,
            task_id=tr_meta.task_id, task_run_id=tr_meta.task_run_id,
            project_ref=tr_meta.project_ref, correlation_id=tr_meta.correlation_id,
            task_revision=2, phase=Phase.TERMINAL, disposition=Disposition.TERMINAL,
            event_cursor=ledger.get_last_sequence(rb_id),
            pending_requests=(),
            snapshot_ref=snapshot.meta.integrity_ref,
            reason=f"finalize complete — outcome: {cv.outcome}",
            causation_ref=cv.meta.integrity_ref,
        )
        _write_obj(ledger, cp, "I1-C", 0)

        ledger.close()

        # Build gate results summary for output
        gate_summary = {}
        for gr in all_gate_results:
            gate_summary[gr.gate_id] = {
                "gate_id": gr.gate_id,
                "outcome": gr.outcome,
                "checked_conditions": list(gr.checked_conditions),
                "supporting_refs": list(gr.supporting_refs),
                "failed_conditions": list(gr.failed_conditions),
                "checked_at": gr.checked_at,
                "evidence_ref": gr.evidence_ref,
            }

        output = {
            "candidate_ref": ce.meta.integrity_ref,
            "evidence_ref": evidences[0].meta.integrity_ref if evidences else None,
            "verification_plan_ref": vplan.meta.integrity_ref,
            "verification_verdict_ref": agg_verdict.meta.integrity_ref,
            "completion_verdict_ref": cv.meta.integrity_ref,
            "task_run_ref": new_tr.meta.integrity_ref,
            "outcome": cv.outcome,
            "completed_items": list(cv.completed_items),
            "incomplete_items": list(cv.incomplete_items),
            "unverified_items": list(cv.unverified_items),
            "residual_risks": list(cv.residual_risks),
            "user_effect": cv.user_effect,
            "gate_results": gate_summary,
        }
        print(canonical_json_dumps(output))
        return 0

    except FurinaContractError as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}), file=sys.stderr)
        return 1
    except Exception as exc:
        print(json.dumps({"error": "INTERNAL_ERROR", "message": str(exc)}), file=sys.stderr)
        return 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="furina-code", description="Furina Code CLI")
    subparsers = parser.add_subparsers(dest="command")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect commands")
    inspect_sub = inspect_parser.add_subparsers(dest="inspect_command")

    prep = inspect_sub.add_parser("prepare", help="Prepare read-only inspection")
    prep.add_argument("--workspace", required=True, help="Path to git repository")
    prep.add_argument("--runtime-dir", required=True, help="Path to runtime directory")
    prep.set_defaults(func=cmd_prepare)

    fin = inspect_sub.add_parser("finalize", help="Finalize with candidate file")
    fin.add_argument("--runtime-dir", required=True, help="Path to runtime directory")
    fin.add_argument("--run-binding-id", required=True, help="Run binding ID from prepare")
    fin.add_argument("--candidate-file", required=True, help="Path to candidate JSON file")
    fin.set_defaults(func=cmd_finalize)

    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    return args.func(args)

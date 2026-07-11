"""Furina Code — CLI entry point for inspect commands."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from .contracts.errors import FurinaContractError
from .contracts.meta import canonical_json_dumps, now_utc
from .contracts.objects import (
    RunBinding,
    TaskDossier,
    TaskRun,
    Checkpoint,
    Phase,
    Disposition,
)
from .ledger.sqlite import Ledger
from .world.snapshot import create_project_snapshot
from .readonly.context import create_context_envelope, write_context_packet
from .backend.candidate import (
    validate_candidate_file,
    validate_candidate_content,
    create_candidate_envelope,
)
from .readonly.verification import (
    create_verification_plan,
    execute_verification,
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


def _write_obj(ledger: Ledger, obj, caller_organ: str, expected_revision: int) -> None:
    """Write any formal object to ledger."""
    payload_fields = {
        "RunBinding": lambda o: {
            "subject_ref": o.subject_ref, "user_ref": o.user_ref,
            "project_ref": o.project_ref, "task_ref": o.task_ref,
            "allowed_tool_classes": list(o.allowed_tool_classes),
            "status": o.status.value, "source_refs": list(o.source_refs),
        },
        "TaskDossier": lambda o: {
            "source_intent_ref": o.source_intent_ref,
            "structured_goal": o.structured_goal,
            "success_criteria": list(o.success_criteria),
            "scope": list(o.scope), "exclusions": list(o.exclusions),
            "unknowns": list(o.unknowns), "risk_class": o.risk_class,
            "user_constraints": list(o.user_constraints),
            "status": o.status.value,
        },
        "TaskRun": lambda o: {
            "task_revision": o.task_revision,
            "phase": o.phase.value, "disposition": o.disposition.value,
            "current_refs": list(o.current_refs),
            "open_requests": list(o.open_requests),
            "started_at": o.started_at.isoformat(),
            "terminal_reason": o.terminal_reason,
        },
        "Checkpoint": lambda o: {
            "task_revision": o.task_revision,
            "phase": o.phase.value, "disposition": o.disposition.value,
            "event_cursor": o.event_cursor,
            "pending_requests": list(o.pending_requests),
            "pending_actions": list(o.pending_actions),
            "snapshot_ref": o.snapshot_ref,
            "ticket_refs": list(o.ticket_refs),
            "reason": o.reason,
        },
        "BackendProfile": lambda o: {
            "backend_id": o.backend_id, "backend_kind": o.backend_kind,
            "capabilities": list(o.capabilities),
            "timeout_seconds": o.timeout_seconds, "status": o.status,
        },
        "ContextEnvelope": lambda o: {
            "snapshot_ref": o.snapshot_ref,
            "task_dossier_ref": o.task_dossier_ref,
            "context_payload": o.context_payload,
            "instruction_profile_id": o.instruction_profile_id,
            "instruction_profile_version": o.instruction_profile_version,
        },
        "CandidateEnvelope": lambda o: {
            "context_envelope_ref": o.context_envelope_ref,
            "candidate_path": o.candidate_path,
            "candidate_sha256": o.candidate_sha256,
            "backend_id": o.backend_id,
            "received_at": o.received_at.isoformat(),
        },
        "ProjectSnapshot": lambda o: {
            "head_sha": o.head_sha, "branch": o.branch,
            "status_lines": list(o.status_lines),
            "tracked_count": o.tracked_count,
            "untracked_count": o.untracked_count,
            "is_clean": o.is_clean,
            "pyproject_exists": o.pyproject_exists,
            "pyproject_sha256": o.pyproject_sha256,
            "requires_python": o.requires_python,
            "runtime_deps": list(o.runtime_deps),
            "dev_deps": list(o.dev_deps),
            "pytest_testpaths": list(o.pytest_testpaths),
            "ci_config_exists": o.ci_config_exists,
            "ci_config_sha256": o.ci_config_sha256,
            "blind_spots": list(o.blind_spots),
            "snapshot_sha256": o.snapshot_sha256,
            "observed_at": o.observed_at.isoformat(),
        },
        "EvidenceEnvelope": lambda o: {
            "evidence_type": o.evidence_type, "source_ref": o.source_ref,
            "claim": o.claim, "supporting_refs": list(o.supporting_refs),
            "integrity_status": o.integrity_status,
            "missing_evidence": list(o.missing_evidence),
        },
        "VerificationPlan": lambda o: {
            "candidate_ref": o.candidate_ref,
            "success_criteria": list(o.success_criteria),
            "steps": list(o.steps),
        },
        "VerificationVerdict": lambda o: {
            "plan_ref": o.plan_ref, "outcome": o.outcome,
            "checked_conditions": list(o.checked_conditions),
            "supporting_refs": list(o.supporting_refs),
            "failed_conditions": list(o.failed_conditions),
            "checked_at": o.checked_at.isoformat(),
        },
        "CompletionVerdict": lambda o: {
            "task_run_ref": o.task_run_ref,
            "candidate_ref": o.candidate_ref, "outcome": o.outcome,
            "completed_items": list(o.completed_items),
            "incomplete_items": list(o.incomplete_items),
            "unverified_items": list(o.unverified_items),
            "residual_risks": list(o.residual_risks),
            "user_effect": o.user_effect,
        },
    }
    builder = payload_fields.get(obj.meta.object_type)
    if builder is None:
        raise ValueError(f"Unknown object type: {obj.meta.object_type}")
    ledger.write_object(obj.meta, builder(obj), caller_organ, expected_revision)


def cmd_prepare(args: argparse.Namespace) -> int:
    """Execute the prepare command."""
    workspace = str(Path(args.workspace).resolve())
    runtime_dir = Path(args.runtime_dir).resolve()
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Validate workspace is a git repo
    git_dir = Path(workspace) / ".git"
    if not git_dir.exists():
        print(json.dumps({"error": "NOT_A_GIT_REPO", "message": f"Not a git repository: {workspace}"}), file=sys.stderr)
        return 2

    ids = _generate_ids()
    db_path = str(runtime_dir / "inspect.sqlite3")

    try:
        ledger = Ledger(db_path)
        ledger.open()

        # 1. RunBinding
        rb = RunBinding.create(
            run_binding_id=ids["run_binding_id"],
            task_id=ids["task_id"], task_run_id=ids["task_run_id"],
            project_ref=ids["project_ref"], correlation_id=ids["correlation_id"],
            subject_ref="cli", user_ref="cli", task_ref=ids["task_id"],
            allowed_tool_classes=("git_read",), source_refs=(),
        )
        _write_obj(ledger, rb, "I1-A", 0)

        # 2. TaskDossier
        td = TaskDossier.create(
            run_binding_id=ids["run_binding_id"],
            task_id=ids["task_id"], task_run_id=ids["task_run_id"],
            project_ref=ids["project_ref"], correlation_id=ids["correlation_id"],
            source_intent_ref="cli:inspect",
            structured_goal="Generate repository baseline report",
            success_criteria=("HEAD observed", "branch observed", "working tree status", "dependencies cataloged"),
            scope=("repository metadata",),
            exclusions=("source code analysis", "code quality", "security audit"),
            unknowns=(),
            risk_class="low",
            user_constraints=("read-only",),
        )
        _write_obj(ledger, td, "I2-A", 0)

        # 3. TaskRun at intake/active
        tr = TaskRun.create(
            run_binding_id=ids["run_binding_id"],
            task_id=ids["task_id"], task_run_id=ids["task_run_id"],
            project_ref=ids["project_ref"], correlation_id=ids["correlation_id"],
            task_revision=1,
        )
        _write_obj(ledger, tr, "I2-D", 0)

        # 4. intake/active → observe/active
        tr = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        _write_obj(ledger, tr, "I2-D", 1)

        # 5. ProjectSnapshot
        snapshot = create_project_snapshot(
            run_binding_id=ids["run_binding_id"],
            task_id=ids["task_id"], task_run_id=ids["task_run_id"],
            project_ref=ids["project_ref"], correlation_id=ids["correlation_id"],
            workspace=workspace,
        )
        _write_obj(ledger, snapshot, "I3-A", 0)

        # 6. observe/active → deliberate/active
        tr = tr.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE)
        _write_obj(ledger, tr, "I2-D", 2)

        # 7. ContextEnvelope
        ctx = create_context_envelope(
            run_binding_id=ids["run_binding_id"],
            task_id=ids["task_id"], task_run_id=ids["task_run_id"],
            project_ref=ids["project_ref"], correlation_id=ids["correlation_id"],
            snapshot=snapshot, dossier=td,
        )
        _write_obj(ledger, ctx, "I2-C", 0)

        # 8. deliberate/active → deliberate/external_blocked
        tr = tr.transition("I2-D", Phase.DELIBERATE, Disposition.EXTERNAL_BLOCKED,
                           current_refs=(snapshot.meta.integrity_ref, ctx.meta.integrity_ref))
        _write_obj(ledger, tr, "I2-D", 3)

        # 9. Checkpoint
        cp = Checkpoint.create(
            run_binding_id=ids["run_binding_id"],
            task_id=ids["task_id"], task_run_id=ids["task_run_id"],
            project_ref=ids["project_ref"], correlation_id=ids["correlation_id"],
            task_revision=1, phase=Phase.DELIBERATE,
            disposition=Disposition.EXTERNAL_BLOCKED,
            event_cursor=ledger.get_last_sequence(ids["run_binding_id"]),
            pending_requests=("candidate_file",),
            snapshot_ref=snapshot.meta.integrity_ref,
            reason="prepare complete — awaiting external candidate",
        )
        _write_obj(ledger, cp, "I1-C", 0)

        ledger.close()

        # Write context packet
        ctx_path = str(runtime_dir / "context_packet.json")
        ctx_digest = write_context_packet(ctx, ctx_path)

        output = {
            "run_binding_id": ids["run_binding_id"],
            "task_id": ids["task_id"],
            "task_run_id": ids["task_run_id"],
            "project_snapshot_ref": snapshot.meta.integrity_ref,
            "backend_profile_ref": "e4-repository-baseline-v1",
            "context_envelope_ref": ctx.meta.integrity_ref,
            "context_packet_path": ctx_path,
            "context_digest": ctx_digest,
            "status": "AWAITING_EXTERNAL_CANDIDATE",
        }
        print(canonical_json_dumps(output))
        return 0

    except FurinaContractError as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}), file=sys.stderr)
        return 1
    except Exception as exc:
        print(json.dumps({"error": "INTERNAL_ERROR", "message": str(exc)}), file=sys.stderr)
        return 3


def cmd_finalize(args: argparse.Namespace) -> int:
    """Execute the finalize command."""
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

        # Load latest TaskRun
        tr_events = ledger.get_verified_events(rb_id)
        tr_evts = [e for e in tr_events if e["event_type"].startswith("TaskRun.")]
        if not tr_evts:
            print(json.dumps({"error": "NO_TASK_RUN", "message": "No TaskRun found"}), file=sys.stderr)
            return 1

        latest_tr_ref = tr_evts[-1]["aggregate_ref"]
        tr_id = latest_tr_ref.split(":", 1)[1] if ":" in latest_tr_ref else latest_tr_ref
        tr_result = ledger.get_latest("TaskRun", tr_id)
        if tr_result is None:
            print(json.dumps({"error": "NO_TASK_RUN", "message": "TaskRun not found"}), file=sys.stderr)
            return 1

        tr_meta, tr_payload = tr_result
        if tr_payload["phase"] != "deliberate" or tr_payload["disposition"] != "external_blocked":
            print(json.dumps({
                "error": "WRONG_PHASE",
                "message": f"TaskRun is {tr_payload['phase']}/{tr_payload['disposition']}, expected deliberate/external_blocked",
            }), file=sys.stderr)
            return 1

        # Load ContextEnvelope
        ctx_events = [e for e in tr_events if e["event_type"].startswith("ContextEnvelope.")]
        if not ctx_events:
            print(json.dumps({"error": "NO_CONTEXT", "message": "No ContextEnvelope found"}), file=sys.stderr)
            return 1

        ctx_ref = ctx_events[-1]["aggregate_ref"]
        ctx_id = ctx_ref.split(":", 1)[1] if ":" in ctx_ref else ctx_ref
        ctx_result = ledger.get_latest("ContextEnvelope", ctx_id)
        if ctx_result is None:
            print(json.dumps({"error": "NO_CONTEXT", "message": "ContextEnvelope not found"}), file=sys.stderr)
            return 1

        ctx_meta, ctx_payload = ctx_result

        # Load ProjectSnapshot
        snap_events = [e for e in tr_events if e["event_type"].startswith("ProjectSnapshot.")]
        if not snap_events:
            print(json.dumps({"error": "NO_SNAPSHOT", "message": "No ProjectSnapshot found"}), file=sys.stderr)
            return 1

        snap_ref = snap_events[-1]["aggregate_ref"]
        snap_id = snap_ref.split(":", 1)[1] if ":" in snap_ref else snap_ref
        snap_result = ledger.get_latest("ProjectSnapshot", snap_id)
        if snap_result is None:
            print(json.dumps({"error": "NO_SNAPSHOT", "message": "ProjectSnapshot not found"}), file=sys.stderr)
            return 1

        snap_meta, snap_payload = snap_result

        # Reconstruct ProjectSnapshot for verification
        from .contracts.objects import ProjectSnapshot as PS
        snapshot = PS(
            meta=snap_meta, head_sha=snap_payload["head_sha"],
            branch=snap_payload["branch"],
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
            blind_spots=tuple(snap_payload.get("blind_spots", [])),
            snapshot_sha256=snap_payload["snapshot_sha256"],
            observed_at=snap_meta.created_at,
        )

        # Validate candidate
        content_text, sha256_hex = validate_candidate_file(candidate_path)

        # Create CandidateEnvelope
        ce = create_candidate_envelope(
            run_binding_id=rb_id,
            task_id=tr_meta.task_id, task_run_id=tr_meta.task_run_id,
            project_ref=tr_meta.project_ref, correlation_id=tr_meta.correlation_id,
            context_envelope_ref=ctx_meta.integrity_ref,
            candidate_path=candidate_path, backend_id="cli-manual",
        )
        _write_obj(ledger, ce, "I2-D", 0)

        # Validate candidate content
        candidate_data = validate_candidate_content(
            content_text, ctx_meta.integrity_ref, "e4-repository-baseline-v1",
        )

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

        # VerificationPlan
        from .readonly.verification import ALL_STEPS
        vplan = create_verification_plan(
            run_binding_id=rb_id,
            task_id=tr_meta.task_id, task_run_id=tr_meta.task_run_id,
            project_ref=tr_meta.project_ref, correlation_id=tr_meta.correlation_id,
            candidate_ref=ce.meta.integrity_ref,
            success_criteria=("HEAD observed", "branch observed"),
        )
        _write_obj(ledger, vplan, "I4-D", 0)

        # Execute verification
        evidences, verdicts = execute_verification(
            run_binding_id=rb_id,
            task_id=tr_meta.task_id, task_run_id=tr_meta.task_run_id,
            project_ref=tr_meta.project_ref, correlation_id=tr_meta.correlation_id,
            plan=vplan, candidate_content=candidate_data, snapshot=snapshot,
        )
        for ev in evidences:
            _write_obj(ledger, ev, "I4-C", 0)
        for vv in verdicts:
            _write_obj(ledger, vv, "I4-D", 0)

        # verify/active → adjudicate/active
        new_tr = new_tr.transition("I2-D", Phase.ADJUDICATE, Disposition.ACTIVE)
        _write_obj(ledger, new_tr, "I2-D", new_tr.meta.revision - 1)

        # CompletionVerdict
        cv = create_completion_verdict(
            run_binding_id=rb_id,
            task_id=tr_meta.task_id, task_run_id=tr_meta.task_run_id,
            project_ref=tr_meta.project_ref, correlation_id=tr_meta.correlation_id,
            task_run_ref=new_tr.meta.integrity_ref,
            candidate_ref=ce.meta.integrity_ref,
            verdicts=verdicts,
        )
        _write_obj(ledger, cv, "I4-E", 0)

        # adjudicate/active → terminal/terminal
        new_tr = new_tr.transition("I2-D", Phase.TERMINAL, Disposition.TERMINAL,
                                   terminal_reason=cv.outcome)
        _write_obj(ledger, new_tr, "I2-D", new_tr.meta.revision - 1)

        # Final checkpoint (use task_revision=2 to differ from prepare's checkpoint)
        cp = Checkpoint.create(
            run_binding_id=rb_id,
            task_id=tr_meta.task_id, task_run_id=tr_meta.task_run_id,
            project_ref=tr_meta.project_ref, correlation_id=tr_meta.correlation_id,
            task_revision=2, phase=Phase.TERMINAL,
            disposition=Disposition.TERMINAL,
            event_cursor=ledger.get_last_sequence(rb_id),
            pending_requests=(),
            snapshot_ref=snapshot.meta.integrity_ref,
            reason=f"finalize complete — outcome: {cv.outcome}",
        )
        _write_obj(ledger, cp, "I1-C", 0)

        ledger.close()

        output = {
            "candidate_ref": ce.meta.integrity_ref,
            "evidence_ref": evidences[0].meta.integrity_ref if evidences else None,
            "verification_plan_ref": vplan.meta.integrity_ref,
            "verification_verdict_ref": verdicts[0].meta.integrity_ref if verdicts else None,
            "completion_verdict_ref": cv.meta.integrity_ref,
            "task_run_ref": new_tr.meta.integrity_ref,
            "outcome": cv.outcome,
            "completed_items": list(cv.completed_items),
            "incomplete_items": list(cv.incomplete_items),
            "unverified_items": list(cv.unverified_items),
            "residual_risks": list(cv.residual_risks),
            "user_effect": cv.user_effect,
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

    # inspect subcommand
    inspect_parser = subparsers.add_parser("inspect", help="Inspect commands")
    inspect_sub = inspect_parser.add_subparsers(dest="inspect_command")

    # prepare
    prep = inspect_sub.add_parser("prepare", help="Prepare read-only inspection")
    prep.add_argument("--workspace", required=True, help="Path to git repository")
    prep.add_argument("--runtime-dir", required=True, help="Path to runtime directory")
    prep.set_defaults(func=cmd_prepare)

    # finalize
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

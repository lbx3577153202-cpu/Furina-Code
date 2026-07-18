"""Executable L3-theory proof for local authority after backend/session loss.

This test deliberately uses a real filesystem write in an isolated Git project,
then closes the SQLite connection before rebuilding the formal authority.  It
does not claim that a real external backend has already been connected; that
handoff remains an integration acceptance obligation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from furina_code.continuity import rebuild_authority_bundle
from furina_code.contracts import BindingMismatch, RunBinding, TaskDossier
from furina_code.experience import extract_completed_write_experience, write_experience_object
from furina_code.initial_loop import run_controlled_write_cycle
from furina_code.ledger import Ledger


def _repo(root: Path) -> Path:
    repo = root / "project"
    repo.mkdir()
    for args in (("init",), ("config", "user.email", "l3@example.test"), ("config", "user.name", "L3 theory")):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True, text=True)
    return repo


def _binding_payload(item: RunBinding) -> dict:
    return {
        "subject_ref": item.subject_ref, "user_ref": item.user_ref,
        "project_ref": item.project_ref, "task_ref": item.task_ref,
        "allowed_tool_classes": list(item.allowed_tool_classes),
        "status": item.status.value, "source_refs": list(item.source_refs),
    }


def _dossier_payload(item: TaskDossier) -> dict:
    return {
        "source_intent_ref": item.source_intent_ref,
        "structured_goal": item.structured_goal,
        "success_criteria": list(item.success_criteria), "scope": list(item.scope),
        "exclusions": list(item.exclusions), "unknowns": list(item.unknowns),
        "risk_class": item.risk_class,
        "user_constraints": list(item.user_constraints), "status": item.status.value,
    }


def test_real_controlled_write_rebuilds_complete_local_authority_after_restart(tmp_path):
    repo = _repo(tmp_path)
    db_path = str(tmp_path / "runtime.sqlite3")
    ledger = Ledger(db_path)
    ledger.open()

    binding = RunBinding.create(
        "rb-l3", "task-l3", "run-l3", "project-l3", "corr-l3",
        subject_ref="furina-local", user_ref="user-l3", task_ref="user:intent:original",
        allowed_tool_classes=("file_write",), source_refs=("user:intent:original",),
    )
    ledger.write_object(binding.meta, _binding_payload(binding), "I1-A", 0)
    dossier = TaskDossier.create(
        "rb-l3", "task-l3", "run-l3", "project-l3", "corr-l3",
        "user:intent:original", "create notes/welcome.txt", ("exact file exists",),
        ("notes/",), ("all other paths",), ("no backend session is authority",),
        "low", ("exact content",), causation_ref=binding.meta.integrity_ref,
    )
    ledger.write_object(dossier.meta, _dossier_payload(dossier), "I2-A", 0)

    cycle = run_controlled_write_cycle(
        ledger, str(repo), run_binding_id="rb-l3", task_id="task-l3", task_run_id="run-l3",
        project_ref="project-l3", correlation_id="corr-l3", candidate_ref="candidate:l3",
        user_authority_refs=("user:explicit-l3",), content="local authority survives restart\n",
        target_path="notes/welcome.txt", task_dossier_ref=dossier.meta.integrity_ref,
    )
    experience = extract_completed_write_experience(cycle.completion)
    write_experience_object(ledger, experience, 0)
    initial_run_meta, _ = ledger.get_revision("TaskRun", "run-l3", 1)
    assert initial_run_meta.causation_ref == dossier.meta.integrity_ref
    assert (repo / "notes" / "welcome.txt").is_file()

    # Simulate loss of the process and every non-local backend/session handle.
    ledger.close()
    fresh_process = Ledger(db_path)
    fresh_process.open()
    bundle = rebuild_authority_bundle(fresh_process, "rb-l3")

    assert bundle.latest_task_dossier_ref == dossier.meta.integrity_ref
    assert bundle.latest_task_run_ref == cycle.task_run.meta.integrity_ref
    assert bundle.unresolved_action_refs == ()
    for object_type in (
        "RunBinding", "TaskDossier", "TaskRun", "ProjectSnapshot", "BoundActionPlan",
        "AuthorizationDecision", "AuthorizationTicket", "ActionReceipt",
        "RealityReconciliation", "VerificationVerdict", "CompletionVerdict", "ExperienceCandidate",
    ):
        assert bundle.object_refs_by_type[object_type]
    fresh_process.close()


def test_authority_bundle_fails_closed_when_task_authority_is_incomplete(tmp_path):
    ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
    ledger.open()
    binding = RunBinding.create(
        "rb-incomplete", "task", "run", "project", "corr",
        "subject", "user", "task", ("file_write",), ("user:intent",),
    )
    ledger.write_object(binding.meta, _binding_payload(binding), "I1-A", 0)

    with pytest.raises(BindingMismatch, match="incomplete"):
        rebuild_authority_bundle(ledger, "rb-incomplete")
    ledger.close()

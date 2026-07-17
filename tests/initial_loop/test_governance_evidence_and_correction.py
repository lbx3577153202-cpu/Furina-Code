"""L3 proof obligations: governance block, evidence expiry and user correction."""

import pytest

from furina_code.contracts import (
    CompletionVerdict,
    ContractInvalid,
    TaskDossier,
    VerificationVerdict,
)
from furina_code.ledger import Ledger
from furina_code.world.controlled_write import (
    evaluate_single_file_authorization,
    issue_single_file_ticket,
    write_e5_object,
)
from furina_code.contracts import BoundActionPlan


def _dossier_payload(item):
    return {
        "source_intent_ref": item.source_intent_ref, "structured_goal": item.structured_goal,
        "success_criteria": list(item.success_criteria), "scope": list(item.scope),
        "exclusions": list(item.exclusions), "unknowns": list(item.unknowns),
        "risk_class": item.risk_class, "user_constraints": list(item.user_constraints),
        "status": item.status.value,
    }


def test_governance_denies_an_out_of_scope_action_before_ticket_issuance():
    plan = BoundActionPlan.create(
        "rb", "task", "run", "project", "corr", "candidate", 1,
        "sha256:snapshot", "sha256:state", ("notes/",),
        ({"kind": "delete_file", "path": "README.md"},), {}, "high",
        "not available", (),
    )
    decision = evaluate_single_file_authorization(plan, "user", ("user:authority",))

    assert decision.decision == "deny"
    with pytest.raises(ContractInvalid, match="Only an allow decision"):
        issue_single_file_ticket(decision, plan)


def test_project_reality_change_supersedes_old_verification_and_completion(tmp_path):
    ledger = Ledger(str(tmp_path / "proof.sqlite3"))
    ledger.open()
    verdict = VerificationVerdict.create(
        "rb", "task", "run", "project", "corr", "sha256:plan", ("sha256:evidence",),
        {"exact": "pass"}, 1.0, outcome="pass", reason="verified",
    )
    completion = CompletionVerdict.create(
        "rb", "task", "run", "project", "corr", 1, "sha256:run", verdict.meta.integrity_ref,
        "candidate", "completed", completed_items=("welcome file",), no_project_side_effect=False,
    )
    write_e5_object(ledger, verdict, 0)
    write_e5_object(ledger, completion, 0)

    invalidated = verdict.invalidate_for_reality_change("target file changed after verification")
    superseded = completion.supersede_for_reality_change(invalidated.meta.integrity_ref, "target file changed after verification")
    write_e5_object(ledger, invalidated, 1)
    write_e5_object(ledger, superseded, 1)

    original_meta, original_payload = ledger.get_revision("VerificationVerdict", verdict.meta.object_id, 1)
    assert original_payload["outcome"] == "pass"
    assert invalidated.outcome == "not_run"
    assert superseded.outcome == "not_completed"
    assert ledger.get_head_revision("CompletionVerdict", completion.meta.object_id) == 2
    ledger.close()


def test_user_correction_creates_new_task_revision_and_preserves_old_direction(tmp_path):
    ledger = Ledger(str(tmp_path / "proof.sqlite3"))
    ledger.open()
    original = TaskDossier.create(
        "rb", "task", "run", "project", "corr", "user:original",
        "create notes/welcome.txt", ("file exists",), ("notes/",),
        ("other paths",), (), "low", ("exact content",),
    )
    corrected = original.revise(
        source_intent_ref="user:correction",
        structured_goal="create notes/greeting.txt",
        success_criteria=("greeting file exists",), scope=("notes/",),
        exclusions=("welcome.txt", "other paths"), unknowns=(), risk_class="low",
        user_constraints=("do not create welcome.txt",),
    )
    ledger.write_object(original.meta, _dossier_payload(original), "I2-A", 0)
    ledger.write_object(corrected.meta, _dossier_payload(corrected), "I2-A", 1)

    _, old_payload = ledger.get_revision("TaskDossier", "task", 1)
    _, new_payload = ledger.get_latest("TaskDossier", "task")
    assert old_payload["structured_goal"] == "create notes/welcome.txt"
    assert new_payload["structured_goal"] == "create notes/greeting.txt"
    assert corrected.meta.supersedes_ref == "TaskDossier:task:rev1"
    ledger.close()

"""B6: Second task determined only after first completion.

Tests that:
1. Second task path/content not created before first completes
2. Experience actually changes the second plan (concrete diff)
3. Authorization remains independent of experience
4. Full causal chain is verified
"""

import subprocess
from pathlib import Path

import pytest

from furina_code.contracts import ContractInvalid
from furina_code.experience import (
    adjudicate_trial,
    extract_completed_write_experience,
    match_experience_for_second_task,
    record_trial_use,
    write_experience_object,
)
from furina_code.initial_loop.controlled_write_cycle import run_controlled_write_cycle
from furina_code.initial_loop.delayed_second_task import (
    plan_second_task_with_experience,
    verify_causal_chain,
)
from furina_code.ledger import Ledger
from furina_code.world.controlled_write import (
    evaluate_single_file_authorization,
    write_e5_object,
)


def _repo(root: Path, name: str) -> Path:
    repo = root / name
    repo.mkdir()
    for args in (("init",), ("config", "user.email", "delayed@test"),
                 ("config", "user.name", "Delayed")):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "README.md").write_bytes(b"fixture\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True, text=True)
    return repo


class TestB6DelayedSecondTask:

    def test_second_task_determined_after_first_completion(self, tmp_path):
        """Second task path/content not created before first completes."""
        from furina_code.world import create_project_snapshot

        first_repo = _repo(tmp_path, "first")
        second_repo = _repo(tmp_path, "second")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        first = run_controlled_write_cycle(
            ledger, str(first_repo), run_binding_id="rb-b6", task_id="task-b6-1",
            task_run_id="run-b6-1", project_ref="project-b6", correlation_id="corr-b6",
            candidate_ref="candidate:b6-1", user_authority_refs=("user:b6",),
            content="First file\n", target_path="notes/first.txt",
        )
        assert first.completion.outcome == "completed"

        experience = extract_completed_write_experience(first.completion)
        write_experience_object(ledger, experience, 0)

        assert not (second_repo / "notes" / "second.txt").exists()

        match = match_experience_for_second_task(
            experience, run_binding_id="rb-b6-2", task_id="task-b6-2",
            task_run_id="run-b6-2", project_ref="project-b6", correlation_id="corr-b6",
            task_revision=1, target_scope=("notes/",), risk="low",
        )
        write_experience_object(ledger, match, 0)
        assert match.recommendation.startswith("candidate_guidance_only")

        second = run_controlled_write_cycle(
            ledger, str(second_repo), run_binding_id="rb-b6-2", task_id="task-b6-2",
            task_run_id="run-b6-2", project_ref="project-b6", correlation_id="corr-b6",
            candidate_ref="candidate:b6-2", user_authority_refs=("user:b6",),
            content="Second file\n", target_path="notes/second.txt",
            experience_match_ref=match.meta.integrity_ref,
        )
        assert second.completion.outcome == "completed"
        assert (second_repo / "notes" / "second.txt").read_bytes() == b"Second file\n"
        assert second.plan.experience_match_ref == match.meta.integrity_ref
        assert second.completion.action_plan_ref == second.plan.meta.integrity_ref

        trial = record_trial_use(experience, match, second.plan, second.completion)
        write_experience_object(ledger, trial, 0)
        lifecycle = adjudicate_trial(experience, trial)
        write_experience_object(ledger, lifecycle, 0)
        assert lifecycle.new_status == "conditional"
        assert lifecycle.new_status != "reusable"
        ledger.close()

    def test_plan_second_task_validates_first_completion(self, tmp_path):
        """plan_second_task_with_experience validates first_completion."""
        from furina_code.world import create_project_snapshot
        from furina_code.contracts import CompletionVerdict

        first_repo = _repo(tmp_path, "first")
        second_repo = _repo(tmp_path, "second")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        first = run_controlled_write_cycle(
            ledger, str(first_repo), run_binding_id="rb-val", task_id="task-val-1",
            task_run_id="run-val-1", project_ref="project-val", correlation_id="corr-val",
            candidate_ref="candidate:val-1", user_authority_refs=("user:val",),
            content="First\n", target_path="notes/first.txt",
        )
        experience = extract_completed_write_experience(first.completion)
        write_experience_object(ledger, experience, 0)

        second_before = create_project_snapshot(
            "rb-val-2", "task-val-2", "run-val-2", "project-val", "corr-val",
            str(second_repo), snapshot_id="task-val-2:snapshot:before",
        )

        # Reject if first_completion is not completed
        not_completed = CompletionVerdict.create(
            "rb-val", "task-val-1", "run-val-1", "project-val", "corr-val",
            1, "sha256:run", "sha256:verification", "candidate:val-1",
            "not_completed",
        )
        with pytest.raises(ContractInvalid, match="completed"):
            plan_second_task_with_experience(
                experience, not_completed,
                run_binding_id="rb-val-2", task_id="task-val-2", task_run_id="run-val-2",
                project_ref="project-val", correlation_id="corr-val", task_revision=1,
                second_target_path="notes/second.txt", second_content="Second\n",
                second_snapshot=second_before,
            )

        # Reject if experience source doesn't match completion
        wrong_completion = CompletionVerdict.create(
            "rb-other", "task-other", "run-other", "project-other", "corr-other",
            1, "sha256:run", "sha256:verification", "candidate:other",
            "completed",
        )
        with pytest.raises(ContractInvalid, match="source must match"):
            plan_second_task_with_experience(
                experience, wrong_completion,
                run_binding_id="rb-val-2", task_id="task-val-2", task_run_id="run-val-2",
                project_ref="project-val", correlation_id="corr-val", task_revision=1,
                second_target_path="notes/second.txt", second_content="Second\n",
                second_snapshot=second_before,
            )
        ledger.close()

    def test_experience_changes_plan_concretely(self, tmp_path):
        """Experience produces measurable plan differences."""
        from furina_code.world import create_project_snapshot

        first_repo = _repo(tmp_path, "first")
        second_repo = _repo(tmp_path, "second")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        first = run_controlled_write_cycle(
            ledger, str(first_repo), run_binding_id="rb-diff", task_id="task-diff-1",
            task_run_id="run-diff-1", project_ref="project-diff", correlation_id="corr-diff",
            candidate_ref="candidate:diff-1", user_authority_refs=("user:diff",),
            content="First\n", target_path="notes/first.txt",
        )
        experience = extract_completed_write_experience(first.completion)
        write_experience_object(ledger, experience, 0)

        second_before = create_project_snapshot(
            "rb-diff-2", "task-diff-2", "run-diff-2", "project-diff", "corr-diff",
            str(second_repo), snapshot_id="task-diff-2:snapshot:before",
        )

        result = plan_second_task_with_experience(
            experience, first.completion,
            run_binding_id="rb-diff-2", task_id="task-diff-2", task_run_id="run-diff-2",
            project_ref="project-diff", correlation_id="corr-diff", task_revision=1,
            second_target_path="notes/second.txt", second_content="Second\n",
            second_snapshot=second_before,
        )

        # Experience was applied
        assert result.experience_was_applied

        # Plans are concretely different: experience_match_ref is set
        assert result.plan_without_experience.experience_match_ref is None
        assert result.plan_with_experience.experience_match_ref is not None
        assert result.experience_match_ref_set

        # The experience_match_ref is a formal field in the plan's payload,
        # which means it participates in integrity hashing and is auditable.
        # This is the concrete difference experience makes to the plan.

        # Authorization is still required and separate
        decision = evaluate_single_file_authorization(result.plan_with_experience, "user", ("user:diff",))
        assert decision.decision == "allow"

        # Without authority, even with experience, authorization denies
        decision_no_auth = evaluate_single_file_authorization(result.plan_with_experience, "user", ())
        assert decision_no_auth.decision == "deny"
        ledger.close()

    def test_causal_chain_integrity(self, tmp_path):
        """Full experience -> match -> plan -> completion chain verified."""
        first_repo = _repo(tmp_path, "first")
        second_repo = _repo(tmp_path, "second")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        first = run_controlled_write_cycle(
            ledger, str(first_repo), run_binding_id="rb-chain", task_id="task-chain-1",
            task_run_id="run-chain-1", project_ref="project-chain", correlation_id="corr-chain",
            candidate_ref="candidate:chain-1", user_authority_refs=("user:chain",),
            content="First\n", target_path="notes/first.txt",
        )
        experience = extract_completed_write_experience(first.completion)
        write_experience_object(ledger, experience, 0)

        match = match_experience_for_second_task(
            experience, run_binding_id="rb-chain-2", task_id="task-chain-2",
            task_run_id="run-chain-2", project_ref="project-chain", correlation_id="corr-chain",
            task_revision=1, target_scope=("notes/",), risk="low",
        )
        write_experience_object(ledger, match, 0)

        second = run_controlled_write_cycle(
            ledger, str(second_repo), run_binding_id="rb-chain-2", task_id="task-chain-2",
            task_run_id="run-chain-2", project_ref="project-chain", correlation_id="corr-chain",
            candidate_ref="candidate:chain-2", user_authority_refs=("user:chain",),
            content="Second\n", target_path="notes/second.txt",
            experience_match_ref=match.meta.integrity_ref,
        )

        assert verify_causal_chain(experience.meta.integrity_ref, match, second.plan, second.completion)
        assert not verify_causal_chain("wrong_ref", match, second.plan, second.completion)
        ledger.close()

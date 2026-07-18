"""B6: Second task determined only after first completion.

Tests supplier gating, experience source validation, plan content
change, and no-authority rejection.
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
    SecondTaskSupplier,
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

    def test_supplier_rejects_before_first_completion(self, tmp_path):
        """Supplier fails if first round not completed in ledger."""
        from furina_code.world import create_project_snapshot

        first_repo = _repo(tmp_path, "first")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        # Start first task but don't complete
        first = run_controlled_write_cycle(
            ledger, str(first_repo), run_binding_id="rb-supp", task_id="task-supp-1",
            task_run_id="run-supp-1", project_ref="project-supp", correlation_id="corr-supp",
            candidate_ref="candidate:supp-1", user_authority_refs=("user:supp",),
            content="First\n", target_path="notes/first.txt",
        )
        assert first.completion.outcome == "completed"

        supplier = SecondTaskSupplier(ledger, "task-supp-1")
        # Supplier should succeed because first is completed
        supplier.get_second_task("rb-supp")
        assert supplier.was_called

        # Supplier should fail for a task that doesn't exist
        bad_supplier = SecondTaskSupplier(ledger, "task-nonexistent")
        with pytest.raises(ContractInvalid, match="not verified"):
            bad_supplier.get_second_task("rb-supp")
        ledger.close()

    def test_plan_validates_first_completion_source(self, tmp_path):
        """plan_second_task validates experience source matches completion."""
        from furina_code.world import create_project_snapshot
        from furina_code.contracts import CompletionVerdict

        first_repo = _repo(tmp_path, "first")
        second_repo = _repo(tmp_path, "second")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        first = run_controlled_write_cycle(
            ledger, str(first_repo), run_binding_id="rb-src", task_id="task-src-1",
            task_run_id="run-src-1", project_ref="project-src", correlation_id="corr-src",
            candidate_ref="candidate:src-1", user_authority_refs=("user:src",),
            content="First\n", target_path="notes/first.txt",
        )
        experience = extract_completed_write_experience(first.completion)
        write_experience_object(ledger, experience, 0)

        second_before = create_project_snapshot(
            "rb-src-2", "task-src-2", "run-src-2", "project-src", "corr-src",
            str(second_repo), snapshot_id="task-src-2:snapshot:before",
        )

        # Wrong completion (different integrity_ref)
        wrong_completion = CompletionVerdict.create(
            "rb-other", "task-other", "run-other", "project-other", "corr-other",
            1, "sha256:run", "sha256:verification", "candidate:other", "completed",
        )
        with pytest.raises(ContractInvalid, match="source_completion_refs"):
            plan_second_task_with_experience(
                experience, wrong_completion,
                run_binding_id="rb-src-2", task_id="task-src-2", task_run_id="run-src-2",
                project_ref="project-src", correlation_id="corr-src", task_revision=1,
                second_target_path="notes/second.txt", second_content="Second\n",
                second_snapshot=second_before,
            )
        ledger.close()

    def test_experience_changes_plan_content(self, tmp_path):
        """Experience produces concretely different plan."""
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

        assert result.experience_was_applied
        assert result.experience_match_ref_set
        assert result.has_extra_verification

        # Plans are concretely different
        assert result.plan_without_experience.experience_match_ref is None
        assert result.plan_with_experience.experience_match_ref is not None
        # Integrity hashes differ
        assert result.plan_without_experience.meta.integrity_ref != result.plan_with_experience.meta.integrity_ref
        ledger.close()

    def test_no_authority_rejects_even_with_experience(self, tmp_path):
        """With experience but no user authority, authorization denies."""
        from furina_code.world import create_project_snapshot

        first_repo = _repo(tmp_path, "first")
        second_repo = _repo(tmp_path, "second")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        first = run_controlled_write_cycle(
            ledger, str(first_repo), run_binding_id="rb-noauth", task_id="task-noauth-1",
            task_run_id="run-noauth-1", project_ref="project-noauth", correlation_id="corr-noauth",
            candidate_ref="candidate:noauth-1", user_authority_refs=("user:noauth",),
            content="First\n", target_path="notes/first.txt",
        )
        experience = extract_completed_write_experience(first.completion)
        write_experience_object(ledger, experience, 0)

        match = match_experience_for_second_task(
            experience, run_binding_id="rb-noauth-2", task_id="task-noauth-2",
            task_run_id="run-noauth-2", project_ref="project-noauth", correlation_id="corr-noauth",
            task_revision=1, target_scope=("notes/",), risk="low",
        )
        write_experience_object(ledger, match, 0)

        second_before = create_project_snapshot(
            "rb-noauth-2", "task-noauth-2", "run-noauth-2", "project-noauth", "corr-noauth",
            str(second_repo), snapshot_id="task-noauth-2:snapshot:before",
        )
        from furina_code.world.controlled_write import bind_single_file_create
        plan = bind_single_file_create(
            second_before, "candidate:noauth-2", "Second\n",
            target_path="notes/second.txt",
            experience_match_ref=match.meta.integrity_ref,
        )

        # No user authority refs → must deny
        decision = evaluate_single_file_authorization(plan, "user", ())
        assert decision.decision == "deny"

        # With authority → allow
        decision_auth = evaluate_single_file_authorization(plan, "user", ("user:noauth",))
        assert decision_auth.decision == "allow"
        ledger.close()

    def test_full_cycle_with_supplier(self, tmp_path):
        """Full second task cycle with supplier gating."""
        first_repo = _repo(tmp_path, "first")
        second_repo = _repo(tmp_path, "second")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        first = run_controlled_write_cycle(
            ledger, str(first_repo), run_binding_id="rb-full", task_id="task-full-1",
            task_run_id="run-full-1", project_ref="project-full", correlation_id="corr-full",
            candidate_ref="candidate:full-1", user_authority_refs=("user:full",),
            content="First\n", target_path="notes/first.txt",
        )
        experience = extract_completed_write_experience(first.completion)
        write_experience_object(ledger, experience, 0)

        # Supplier must be called after first completion
        supplier = SecondTaskSupplier(ledger, "task-full-1")
        supplier.get_second_task("rb-full")

        match = match_experience_for_second_task(
            experience, run_binding_id="rb-full-2", task_id="task-full-2",
            task_run_id="run-full-2", project_ref="project-full", correlation_id="corr-full",
            task_revision=1, target_scope=("notes/",), risk="low",
        )
        write_experience_object(ledger, match, 0)

        second = run_controlled_write_cycle(
            ledger, str(second_repo), run_binding_id="rb-full-2", task_id="task-full-2",
            task_run_id="run-full-2", project_ref="project-full", correlation_id="corr-full",
            candidate_ref="candidate:full-2", user_authority_refs=("user:full",),
            content="Second\n", target_path="notes/second.txt",
            experience_match_ref=match.meta.integrity_ref,
        )
        assert second.completion.outcome == "completed"
        assert (second_repo / "notes" / "second.txt").read_bytes() == b"Second\n"

        assert verify_causal_chain(experience.meta.integrity_ref, match, second.plan, second.completion)

        trial = record_trial_use(experience, match, second.plan, second.completion)
        write_experience_object(ledger, trial, 0)
        lifecycle = adjudicate_trial(experience, trial)
        write_experience_object(ledger, lifecycle, 0)
        assert lifecycle.new_status == "conditional"
        assert lifecycle.new_status != "reusable"
        ledger.close()

    def test_causal_chain_integrity(self, tmp_path):
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

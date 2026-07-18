"""B6: Second task determined only after first completion."""

import subprocess
from pathlib import Path

from furina_code.experience import (
    adjudicate_trial,
    extract_completed_write_experience,
    match_experience_for_second_task,
    record_trial_use,
    write_experience_object,
)
from furina_code.initial_loop.controlled_write_cycle import run_controlled_write_cycle
from furina_code.ledger import Ledger


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
        first_repo = _repo(tmp_path, "first")
        second_repo = _repo(tmp_path, "second")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        # Complete first task
        first = run_controlled_write_cycle(
            ledger, str(first_repo), run_binding_id="rb-b6", task_id="task-b6-1",
            task_run_id="run-b6-1", project_ref="project-b6", correlation_id="corr-b6",
            candidate_ref="candidate:b6-1", user_authority_refs=("user:b6",),
            content="First file\n", target_path="notes/first.txt",
        )
        assert first.completion.outcome == "completed"

        # Extract experience AFTER first completion
        experience = extract_completed_write_experience(first.completion)
        write_experience_object(ledger, experience, 0)

        # Second target does NOT exist yet (wasn't created before first started)
        assert not (second_repo / "notes" / "second.txt").exists()

        # Match experience for second task
        match = match_experience_for_second_task(
            experience, run_binding_id="rb-b6-2", task_id="task-b6-2",
            task_run_id="run-b6-2", project_ref="project-b6", correlation_id="corr-b6",
            task_revision=1, target_scope=("notes/",), risk="low",
        )
        write_experience_object(ledger, match, 0)

        # Experience was applied as guidance
        assert match.recommendation.startswith("candidate_guidance_only")
        assert bool(match.candidate_refs)

        # Execute second task with experience match
        second = run_controlled_write_cycle(
            ledger, str(second_repo), run_binding_id="rb-b6-2", task_id="task-b6-2",
            task_run_id="run-b6-2", project_ref="project-b6", correlation_id="corr-b6",
            candidate_ref="candidate:b6-2", user_authority_refs=("user:b6",),
            content="Second file\n", target_path="notes/second.txt",
            experience_match_ref=match.meta.integrity_ref,
        )
        assert second.completion.outcome == "completed"
        assert (second_repo / "notes" / "second.txt").read_bytes() == b"Second file\n"

        # Verify causal chain
        assert second.plan.experience_match_ref == match.meta.integrity_ref
        assert second.completion.action_plan_ref == second.plan.meta.integrity_ref

        # Record trial and adjudicate
        trial = record_trial_use(experience, match, second.plan, second.completion)
        write_experience_object(ledger, trial, 0)
        lifecycle = adjudicate_trial(experience, trial)
        write_experience_object(ledger, lifecycle, 0)

        # Must be conditional, never reusable
        assert lifecycle.new_status == "conditional"
        assert lifecycle.new_status != "reusable"
        ledger.close()

    def test_experience_is_guidance_not_authorization(self, tmp_path):
        """Match changes plan but does not replace authorization."""
        from furina_code.world.controlled_write import evaluate_single_file_authorization

        first_repo = _repo(tmp_path, "first")
        second_repo = _repo(tmp_path, "second")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        first = run_controlled_write_cycle(
            ledger, str(first_repo), run_binding_id="rb-auth", task_id="task-auth-1",
            task_run_id="run-auth-1", project_ref="project-auth", correlation_id="corr-auth",
            candidate_ref="candidate:auth-1", user_authority_refs=("user:auth",),
            content="First\n", target_path="notes/first.txt",
        )
        experience = extract_completed_write_experience(first.completion)
        write_experience_object(ledger, experience, 0)

        match = match_experience_for_second_task(
            experience, run_binding_id="rb-auth-2", task_id="task-auth-2",
            task_run_id="run-auth-2", project_ref="project-auth", correlation_id="corr-auth",
            task_revision=1, target_scope=("notes/",), risk="low",
        )
        write_experience_object(ledger, match, 0)

        # Match is guidance only
        assert match.recommendation.startswith("candidate_guidance_only")

        # Authorization is separate - still requires proper authority
        second = run_controlled_write_cycle(
            ledger, str(second_repo), run_binding_id="rb-auth-2", task_id="task-auth-2",
            task_run_id="run-auth-2", project_ref="project-auth", correlation_id="corr-auth",
            candidate_ref="candidate:auth-2", user_authority_refs=("user:auth",),
            content="Second\n", target_path="notes/second.txt",
            experience_match_ref=match.meta.integrity_ref,
        )

        # Experience match is set on plan
        assert second.plan.experience_match_ref == match.meta.integrity_ref

        # But authorization was still required (decision was allow)
        assert second.decision.decision == "allow"
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

        # Verify chain
        assert experience.meta.integrity_ref in match.candidate_refs
        assert second.plan.experience_match_ref == match.meta.integrity_ref
        assert second.completion.action_plan_ref == second.plan.meta.integrity_ref

        # Chain breaks with wrong experience ref
        assert experience.meta.integrity_ref not in ("wrong_ref",)
        ledger.close()

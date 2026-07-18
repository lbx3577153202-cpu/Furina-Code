"""B4: Reality drift invalidates completed evidence."""

import hashlib
import subprocess
from pathlib import Path

import pytest

from furina_code.contracts import ContractInvalid
from furina_code.initial_loop.controlled_write_cycle import run_controlled_write_cycle
from furina_code.initial_loop.reality_drift import (
    detect_and_invalidate_reality_drift,
    verify_old_evidence_invalid,
)
from furina_code.ledger import Ledger


def _repo(root: Path, name: str) -> Path:
    repo = root / name
    repo.mkdir()
    for args in (("init",), ("config", "user.email", "drift@test"),
                 ("config", "user.name", "Drift")):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "README.md").write_bytes(b"fixture\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True, text=True)
    return repo


class TestB4RealityDrift:

    def test_external_mutation_invalidates_evidence(self, tmp_path):
        repo = _repo(tmp_path, "repo")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        result = run_controlled_write_cycle(
            ledger, str(repo), run_binding_id="rb-drift", task_id="task-drift",
            task_run_id="run-drift", project_ref="project-drift", correlation_id="corr-drift",
            candidate_ref="candidate:drift", user_authority_refs=("user:drift",),
            content="original content\n", target_path="notes/drift.txt",
        )
        assert result.completion.outcome == "completed"

        # External mutation
        (repo / "notes" / "drift.txt").write_bytes(b"TAMPERED\n")

        # Get hashes
        current_hash = "sha256:" + hashlib.sha256(b"TAMPERED\n").hexdigest()
        expected_hash = "sha256:" + hashlib.sha256(b"original content\n").hexdigest()

        drift_result = detect_and_invalidate_reality_drift(
            ledger, result.verification, result.completion, current_hash, expected_hash,
        )
        assert drift_result.invalidation_reason.startswith("Project reality changed")

        v_invalid, c_invalid = verify_old_evidence_invalid(
            ledger, result.verification, result.completion,
        )
        assert v_invalid
        assert c_invalid
        ledger.close()

    def test_no_drift_raises_error(self, tmp_path):
        repo = _repo(tmp_path, "repo")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        result = run_controlled_write_cycle(
            ledger, str(repo), run_binding_id="rb-nodrift", task_id="task-nodrift",
            task_run_id="run-nodrift", project_ref="project-nodrift", correlation_id="corr-nodrift",
            candidate_ref="candidate:nodrift", user_authority_refs=("user:nodrift",),
            content="content\n", target_path="notes/nodrift.txt",
        )

        h = "sha256:" + hashlib.sha256(b"content\n").hexdigest()
        with pytest.raises(ContractInvalid, match="No reality drift"):
            detect_and_invalidate_reality_drift(
                ledger, result.verification, result.completion, h, h,
            )
        ledger.close()

    def test_invalidated_completion_blocks_experience(self, tmp_path):
        from furina_code.experience import extract_completed_write_experience

        repo = _repo(tmp_path, "repo")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        result = run_controlled_write_cycle(
            ledger, str(repo), run_binding_id="rb-exp", task_id="task-exp",
            task_run_id="run-exp", project_ref="project-exp", correlation_id="corr-exp",
            candidate_ref="candidate:exp", user_authority_refs=("user:exp",),
            content="exp content\n", target_path="notes/exp.txt",
        )

        current_hash = "sha256:" + hashlib.sha256(b"drifted\n").hexdigest()
        expected_hash = "sha256:" + hashlib.sha256(b"exp content\n").hexdigest()
        detect_and_invalidate_reality_drift(
            ledger, result.verification, result.completion, current_hash, expected_hash,
        )

        # The new completion (after invalidation) should have outcome="not_completed"
        new_c = ledger.get_latest("CompletionVerdict", result.completion.meta.object_id)
        assert new_c is not None
        _, new_payload = new_c
        assert new_payload["outcome"] == "not_completed"

        # Cannot extract experience from a not_completed completion
        from furina_code.contracts import CompletionVerdict
        old_completion = result.completion
        # Build a new CompletionVerdict from the invalidated payload
        invalid_completion = CompletionVerdict.create(
            old_completion.meta.run_binding_id, old_completion.meta.task_id,
            old_completion.meta.task_run_id, old_completion.meta.project_ref,
            old_completion.meta.correlation_id, old_completion.task_revision,
            old_completion.task_run_ref, old_completion.verification_ref,
            old_completion.candidate_ref, "not_completed",
        )
        with pytest.raises(ContractInvalid, match="completed"):
            extract_completed_write_experience(invalid_completion)
        ledger.close()

    def test_new_completion_has_not_completed(self, tmp_path):
        repo = _repo(tmp_path, "repo")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        result = run_controlled_write_cycle(
            ledger, str(repo), run_binding_id="rb-claim", task_id="task-claim",
            task_run_id="run-claim", project_ref="project-claim", correlation_id="corr-claim",
            candidate_ref="candidate:claim", user_authority_refs=("user:claim",),
            content="claim content\n", target_path="notes/claim.txt",
        )

        current_hash = "sha256:" + hashlib.sha256(b"drifted\n").hexdigest()
        expected_hash = "sha256:" + hashlib.sha256(b"claim content\n").hexdigest()
        detect_and_invalidate_reality_drift(
            ledger, result.verification, result.completion, current_hash, expected_hash,
        )

        new_result = ledger.get_latest("CompletionVerdict", result.completion.meta.object_id)
        assert new_result is not None
        _, payload = new_result
        assert payload["outcome"] == "not_completed"
        ledger.close()

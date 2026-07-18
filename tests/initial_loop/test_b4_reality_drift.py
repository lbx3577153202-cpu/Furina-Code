"""B4: Reality drift invalidates completed evidence.

Tests that real external file modification is detected against
plan.expected_diff and old evidence is automatically invalidated.
"""

import hashlib
import subprocess
from pathlib import Path

import pytest

from furina_code.contracts import ContractInvalid
from furina_code.initial_loop.controlled_write_cycle import run_controlled_write_cycle
from furina_code.initial_loop.reality_drift import (
    detect_and_invalidate_reality_drift,
    observe_target,
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

    def test_observe_reads_real_filesystem(self, tmp_path):
        """observe_target reads the actual file."""
        repo = _repo(tmp_path, "repo")
        (repo / "notes").mkdir()
        (repo / "notes" / "target.txt").write_bytes(b"original\n")

        h = observe_target(str(repo), "notes/target.txt")
        assert h == "sha256:" + hashlib.sha256(b"original\n").hexdigest()

        (repo / "notes" / "target.txt").write_bytes(b"CHANGED\n")
        h2 = observe_target(str(repo), "notes/target.txt")
        assert h2 == "sha256:" + hashlib.sha256(b"CHANGED\n").hexdigest()
        assert h != h2

    def test_observe_rejects_escape(self, tmp_path):
        """Path traversal is rejected."""
        repo = _repo(tmp_path, "repo")
        with pytest.raises(ContractInvalid, match="Path traversal"):
            observe_target(str(repo), "../../../etc/passwd")

    def test_observe_rejects_absolute(self, tmp_path):
        """Absolute path is rejected."""
        repo = _repo(tmp_path, "repo")
        with pytest.raises(ContractInvalid, match="Absolute path"):
            observe_target(str(repo), "/etc/passwd")

    def test_real_modification_invalidates_evidence(self, tmp_path):
        """Real external modification triggers invalidation."""
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

        # REAL external modification
        (repo / "notes" / "drift.txt").write_bytes(b"TAMPERED content\n")

        drift_result = detect_and_invalidate_reality_drift(
            ledger, result.verification, result.completion, result.plan, str(repo),
        )
        assert drift_result.observed_hash == "sha256:" + hashlib.sha256(b"TAMPERED content\n").hexdigest()
        assert drift_result.expected_hash == result.plan.expected_diff["content_sha256"]

        v_invalid, c_invalid = verify_old_evidence_invalid(
            ledger, result.verification, result.completion,
        )
        assert v_invalid
        assert c_invalid
        ledger.close()

    def test_no_drift_raises_error(self, tmp_path):
        """When file unchanged, detect raises."""
        repo = _repo(tmp_path, "repo")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        result = run_controlled_write_cycle(
            ledger, str(repo), run_binding_id="rb-nodrift", task_id="task-nodrift",
            task_run_id="run-nodrift", project_ref="project-nodrift", correlation_id="corr-nodrift",
            candidate_ref="candidate:nodrift", user_authority_refs=("user:nodrift",),
            content="content\n", target_path="notes/nodrift.txt",
        )

        with pytest.raises(ContractInvalid, match="No reality drift"):
            detect_and_invalidate_reality_drift(
                ledger, result.verification, result.completion, result.plan, str(repo),
            )
        ledger.close()

    def test_invalidated_completion_blocks_experience(self, tmp_path):
        """Invalidated completion cannot be used for experience promotion."""
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

        # REAL modification
        (repo / "notes" / "exp.txt").write_bytes(b"drifted\n")

        detect_and_invalidate_reality_drift(
            ledger, result.verification, result.completion, result.plan, str(repo),
        )

        # Query ledger for current completion (should be not_completed)
        new_c = ledger.get_latest("CompletionVerdict", result.completion.meta.object_id)
        assert new_c is not None
        _, payload = new_c
        assert payload["outcome"] == "not_completed"

        # Cannot extract experience from not_completed (query ledger, not memory)
        from furina_code.contracts import CompletionVerdict
        invalid = CompletionVerdict.create(
            result.completion.meta.run_binding_id, result.completion.meta.task_id,
            result.completion.meta.task_run_id, result.completion.meta.project_ref,
            result.completion.meta.correlation_id, result.completion.task_revision,
            result.completion.task_run_ref, result.completion.verification_ref,
            result.completion.candidate_ref, "not_completed",
        )
        with pytest.raises(ContractInvalid, match="completed"):
            extract_completed_write_experience(invalid)
        ledger.close()

    def test_new_completion_has_not_completed(self, tmp_path):
        """After drift, new completion outcome is not_completed."""
        repo = _repo(tmp_path, "repo")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        result = run_controlled_write_cycle(
            ledger, str(repo), run_binding_id="rb-claim", task_id="task-claim",
            task_run_id="run-claim", project_ref="project-claim", correlation_id="corr-claim",
            candidate_ref="candidate:claim", user_authority_refs=("user:claim",),
            content="claim content\n", target_path="notes/claim.txt",
        )

        # REAL modification
        (repo / "notes" / "claim.txt").write_bytes(b"drifted\n")

        detect_and_invalidate_reality_drift(
            ledger, result.verification, result.completion, result.plan, str(repo),
        )

        new_result = ledger.get_latest("CompletionVerdict", result.completion.meta.object_id)
        assert new_result is not None
        _, payload = new_result
        assert payload["outcome"] == "not_completed"
        ledger.close()

    def test_file_deletion_detected(self, tmp_path):
        """Deleted file is detected as drift."""
        repo = _repo(tmp_path, "repo")
        ledger = Ledger(str(tmp_path / "runtime.sqlite3"))
        ledger.open()

        result = run_controlled_write_cycle(
            ledger, str(repo), run_binding_id="rb-del", task_id="task-del",
            task_run_id="run-del", project_ref="project-del", correlation_id="corr-del",
            candidate_ref="candidate:del", user_authority_refs=("user:del",),
            content="to be deleted\n", target_path="notes/del.txt",
        )

        # Delete the file
        (repo / "notes" / "del.txt").unlink()

        drift_result = detect_and_invalidate_reality_drift(
            ledger, result.verification, result.completion, result.plan, str(repo),
        )
        assert drift_result.observed_hash == "deleted"
        assert "deleted" in drift_result.invalidation_reason
        ledger.close()

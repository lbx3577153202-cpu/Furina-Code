"""E4 tests — verification logic."""

import pytest
from furina_code.contracts import ProjectSnapshot
from furina_code.readonly.verification import (
    create_verification_plan,
    verify_candidate_against_snapshot,
    execute_verification,
    ALL_STEPS,
)


def _make_snapshot(**overrides):
    defaults = dict(
        run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
        project_ref="p", correlation_id="c",
        head_sha="a" * 40, branch="main", status_lines=(),
        tracked_count=10, untracked_count=0, is_clean=True,
        pyproject_exists=True, pyproject_sha256="sha256:abc",
        requires_python=">=3.12", runtime_deps=(), dev_deps=("pytest",),
        pytest_testpaths=("tests",), ci_config_exists=True,
        ci_config_sha256="sha256:def", blind_spots=(),
        snapshot_sha256="sha256:123",
    )
    defaults.update(overrides)
    return ProjectSnapshot.create(**defaults)


def _make_candidate(**content_overrides):
    defaults = {
        "repository_head": "a" * 40,
        "branch": "main",
        "working_tree": "clean",
        "tracked_file_count": 10,
        "untracked_file_count": 0,
        "python_requires": ">=3.12",
        "runtime_dependencies": [],
        "dev_dependencies": ["pytest"],
        "pytest_testpaths": ["tests"],
        "ci_config": {"present": True, "sha256": "sha256:def"},
        "blind_spots": [],
        "summary": "test",
    }
    defaults.update(content_overrides)
    return {"content": defaults}


class TestVerifyAgainstSnapshot:
    def test_head_match(self):
        snap = _make_snapshot()
        cand = _make_candidate()
        passed, msg = verify_candidate_against_snapshot(cand, snap, "snapshot_head_match")
        assert passed is True

    def test_head_mismatch(self):
        snap = _make_snapshot()
        cand = _make_candidate(repository_head="b" * 40)
        passed, msg = verify_candidate_against_snapshot(cand, snap, "snapshot_head_match")
        assert passed is False

    def test_branch_match(self):
        snap = _make_snapshot()
        cand = _make_candidate()
        passed, _ = verify_candidate_against_snapshot(cand, snap, "snapshot_branch_match")
        assert passed is True

    def test_branch_mismatch(self):
        snap = _make_snapshot()
        cand = _make_candidate(branch="develop")
        passed, _ = verify_candidate_against_snapshot(cand, snap, "snapshot_branch_match")
        assert passed is False

    def test_clean_match(self):
        snap = _make_snapshot()
        cand = _make_candidate()
        passed, _ = verify_candidate_against_snapshot(cand, snap, "snapshot_clean_match")
        assert passed is True

    def test_dirty_mismatch(self):
        snap = _make_snapshot(is_clean=False)
        cand = _make_candidate(working_tree="clean")
        passed, _ = verify_candidate_against_snapshot(cand, snap, "snapshot_clean_match")
        assert passed is False

    def test_file_count_match(self):
        snap = _make_snapshot()
        cand = _make_candidate()
        passed, _ = verify_candidate_against_snapshot(cand, snap, "snapshot_file_count_match")
        assert passed is True

    def test_file_count_mismatch(self):
        snap = _make_snapshot()
        cand = _make_candidate(tracked_file_count=99)
        passed, _ = verify_candidate_against_snapshot(cand, snap, "snapshot_file_count_match")
        assert passed is False

    def test_python_requires_match(self):
        snap = _make_snapshot()
        cand = _make_candidate()
        passed, _ = verify_candidate_against_snapshot(cand, snap, "snapshot_python_requires_match")
        assert passed is True

    def test_python_requires_mismatch(self):
        snap = _make_snapshot()
        cand = _make_candidate(python_requires=">=3.10")
        passed, _ = verify_candidate_against_snapshot(cand, snap, "snapshot_python_requires_match")
        assert passed is False

    def test_runtime_deps_match(self):
        snap = _make_snapshot()
        cand = _make_candidate()
        passed, _ = verify_candidate_against_snapshot(cand, snap, "snapshot_runtime_deps_match")
        assert passed is True

    def test_dev_deps_match(self):
        snap = _make_snapshot()
        cand = _make_candidate()
        passed, _ = verify_candidate_against_snapshot(cand, snap, "snapshot_dev_deps_match")
        assert passed is True

    def test_pytest_testpaths_match(self):
        snap = _make_snapshot()
        cand = _make_candidate()
        passed, _ = verify_candidate_against_snapshot(cand, snap, "snapshot_pytest_testpaths_match")
        assert passed is True

    def test_ci_config_match(self):
        snap = _make_snapshot()
        cand = _make_candidate()
        passed, _ = verify_candidate_against_snapshot(cand, snap, "snapshot_ci_config_match")
        assert passed is True

    def test_blind_spots_match(self):
        snap = _make_snapshot()
        cand = _make_candidate()
        passed, _ = verify_candidate_against_snapshot(cand, snap, "snapshot_blind_spots_match")
        assert passed is True

    def test_unknown_step_raises(self):
        snap = _make_snapshot()
        cand = _make_candidate()
        with pytest.raises(Exception):
            verify_candidate_against_snapshot(cand, snap, "nonexistent_step")


class TestExecuteVerification:
    def test_all_pass(self):
        snap = _make_snapshot()
        cand = _make_candidate()
        plan = create_verification_plan(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            candidate_ref="sha256:abc", success_criteria=("HEAD",),
        )
        evidences, verdicts = execute_verification(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            plan=plan, candidate_content=cand, snapshot=snap,
        )
        assert len(verdicts) == len(ALL_STEPS)
        assert all(v.outcome == "pass" for v in verdicts)
        assert len(evidences) == len(ALL_STEPS)

    def test_one_fails(self):
        snap = _make_snapshot()
        cand = _make_candidate(repository_head="b" * 40)
        plan = create_verification_plan(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            candidate_ref="sha256:abc", success_criteria=("HEAD",),
        )
        evidences, verdicts = execute_verification(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            plan=plan, candidate_content=cand, snapshot=snap,
        )
        head_verdict = [v for v in verdicts if "head" in v.checked_conditions[0]][0]
        assert head_verdict.outcome == "fail"

    def test_evidence_has_supporting_refs(self):
        snap = _make_snapshot()
        cand = _make_candidate()
        plan = create_verification_plan(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            candidate_ref="sha256:abc", success_criteria=(),
        )
        evidences, _ = execute_verification(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            plan=plan, candidate_content=cand, snapshot=snap,
        )
        for ev in evidences:
            assert len(ev.supporting_refs) > 0

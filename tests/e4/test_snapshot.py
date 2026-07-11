"""E4 tests — ProjectSnapshot creation."""

import subprocess
from pathlib import Path
from furina_code.world.snapshot import create_project_snapshot


class TestProjectSnapshot:
    def test_create_from_real_repo(self):
        repo = str(Path(__file__).resolve().parents[2])
        snap = create_project_snapshot(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c", workspace=repo,
        )
        assert snap.meta.object_type == "ProjectSnapshot"
        assert len(snap.head_sha) == 40
        assert snap.tracked_count > 0
        assert snap.pyproject_exists is True
        assert snap.requires_python is not None
        assert snap.snapshot_sha256.startswith("sha256:")

    def test_deterministic_sha(self):
        repo = str(Path(__file__).resolve().parents[2])
        snap1 = create_project_snapshot(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c", workspace=repo,
        )
        snap2 = create_project_snapshot(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c", workspace=repo,
        )
        # Same observation → same sha (assuming no file changes between calls)
        assert snap1.snapshot_sha256 == snap2.snapshot_sha256

    def test_snapshot_with_no_pyproject(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, shell=False)
        subprocess.run(["git", "config", "user.email", "test@test.com"],
                       cwd=str(repo), capture_output=True, shell=False)
        subprocess.run(["git", "config", "user.name", "Test"],
                       cwd=str(repo), capture_output=True, shell=False)
        (repo / "test.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, shell=False)
        subprocess.run(["git", "commit", "-m", "init"],
                       cwd=str(repo), capture_output=True, shell=False)

        snap = create_project_snapshot(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c", workspace=str(repo),
        )
        assert snap.pyproject_exists is False
        assert snap.requires_python is None
        assert "pyproject.toml missing" in snap.blind_spots[0]

    def test_snapshot_write_to_ledger(self, tmp_path):
        from furina_code.ledger import Ledger
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, shell=False)
        subprocess.run(["git", "config", "user.email", "test@test.com"],
                       cwd=str(repo), capture_output=True, shell=False)
        subprocess.run(["git", "config", "user.name", "Test"],
                       cwd=str(repo), capture_output=True, shell=False)
        (repo / "test.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, shell=False)
        subprocess.run(["git", "commit", "-m", "init"],
                       cwd=str(repo), capture_output=True, shell=False)

        snap = create_project_snapshot(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c", workspace=str(repo),
        )

        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        ledger.write_object(snap.meta, {
            "head_sha": snap.head_sha, "branch": snap.branch,
            "status_lines": list(snap.status_lines),
            "tracked_count": snap.tracked_count,
            "untracked_count": snap.untracked_count,
            "is_clean": snap.is_clean,
            "pyproject_exists": snap.pyproject_exists,
            "pyproject_sha256": snap.pyproject_sha256,
            "requires_python": snap.requires_python,
            "runtime_deps": list(snap.runtime_deps),
            "dev_deps": list(snap.dev_deps),
            "pytest_testpaths": list(snap.pytest_testpaths),
            "ci_config_exists": snap.ci_config_exists,
            "ci_config_sha256": snap.ci_config_sha256,
            "blind_spots": list(snap.blind_spots),
            "snapshot_sha256": snap.snapshot_sha256,
            "observed_at": snap.observed_at.isoformat(),
        }, caller_organ="I3-A", expected_revision=0)
        assert ledger.get_head_revision("ProjectSnapshot", snap.meta.object_id) == 1
        ledger.close()

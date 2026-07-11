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
        assert snap.observation_scope == "read-only repository baseline"
        assert snap.freshness_policy == "point-in-time"
        assert snap.head_sha is not None

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

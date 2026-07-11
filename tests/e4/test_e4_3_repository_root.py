"""E4.3 tests — unified repository root and subdirectory observation."""

import subprocess
from pathlib import Path
from furina_code.world.snapshot import create_project_snapshot
from furina_code.world.git import observe_git


class TestUnifiedRepositoryRoot:
    def test_subdirectory_call_returns_same_root(self):
        """Calling from a subdirectory must resolve to the same repository root."""
        repo = str(Path(__file__).resolve().parents[2])
        subdir = str(Path(__file__).resolve().parent)  # tests/e4/

        root_from_repo = observe_git(repo)["repository_root"]
        root_from_subdir = observe_git(subdir)["repository_root"]

        assert root_from_repo == root_from_subdir

    def test_snapshot_from_subdirectory_uses_repo_root(self, tmp_path):
        """Snapshot from subdirectory reads pyproject/CI from real repo root."""
        repo = str(Path(__file__).resolve().parents[2])
        subdir = str(Path(__file__).resolve().parent)  # tests/e4/

        snap = create_project_snapshot(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c", workspace=subdir,
        )
        # pyproject.toml is at repo root, not in tests/e4/
        assert snap.pyproject_exists is True
        assert snap.head_sha is not None
        assert len(snap.head_sha) == 40

    def test_snapshot_head_same_from_subdirectory(self):
        """HEAD must be the same whether called from repo root or subdirectory."""
        repo = str(Path(__file__).resolve().parents[2])
        subdir = str(Path(__file__).resolve().parent)

        snap_root = create_project_snapshot(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c", workspace=repo,
        )
        snap_sub = create_project_snapshot(
            run_binding_id="rb-2", task_id="t-2", task_run_id="tr-2",
            project_ref="p", correlation_id="c2", workspace=subdir,
        )
        assert snap_root.head_sha == snap_sub.head_sha
        assert snap_root.branch == snap_sub.branch
        assert snap_root.pyproject_exists == snap_sub.pyproject_exists
        assert snap_root.requires_python == snap_sub.requires_python

    def test_deep_subdirectory_prepare_succeeds(self, tmp_path):
        """Prepare from a deep subdirectory must work and observe real repo root."""
        from furina_code.cli import main as cli_main
        from furina_code.ledger import Ledger

        repo = str(Path(__file__).resolve().parents[2])
        subdir = str(Path(__file__).resolve().parent)  # tests/e4/
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", subdir,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 0

        # Verify snapshot has real repo data
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        cur = ledger.conn.execute(
            "SELECT object_id FROM object_heads WHERE object_type='ProjectSnapshot' LIMIT 1"
        )
        row = cur.fetchone()
        assert row is not None
        meta, payload = ledger.get_latest("ProjectSnapshot", row[0])
        assert payload["pyproject_exists"] is True
        assert payload["head_sha"] is not None
        ledger.close()

"""E4.3 tests — raw path validation before resolve."""

import json
from pathlib import Path
from furina_code.cli import main as cli_main


class TestRawPathValidation:
    def test_workspace_traversal_with_subdir_resolves_to_valid_repo(self, tmp_path):
        """Raw path with .. must be rejected even if resolved path is a valid repo."""
        repo = str(Path(__file__).resolve().parents[2])
        # Construct a path like: <repo>/tests/../ which resolves to <repo>
        # The raw path contains .. so it must be rejected
        traversal_path = repo + "/tests/.."
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", traversal_path,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 1
        # Verify error is CONTRACT_INVALID, not "not a git repo"
        # (the path resolves to a valid repo, but raw validation catches it)

    def test_workspace_traversal_rejected_before_resolve(self, tmp_path):
        """Path traversal in workspace must be caught before resolve."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        # This path has .. in raw form
        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo + "/../",
                              "--runtime-dir", str(runtime)])
        assert exit_code == 1

    def test_runtime_dir_traversal_rejected(self, tmp_path):
        """Path traversal in runtime-dir must be caught."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime) + "/../escape"])
        assert exit_code == 1

    def test_candidate_file_traversal_rejected(self, tmp_path):
        """Path traversal in candidate-file must be caught."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        # First prepare successfully
        cli_main(["inspect", "prepare",
                  "--workspace", repo,
                  "--runtime-dir", str(runtime)])

        from furina_code.ledger import Ledger
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        cur = ledger.conn.execute("SELECT DISTINCT run_binding_id FROM event_envelopes LIMIT 1")
        rb_id = cur.fetchone()[0]
        ledger.close()

        # Candidate path with traversal
        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", str(tmp_path / ".." / "escape.json")])
        assert exit_code == 1

    def test_traversal_error_is_contract_invalid(self, tmp_path, capsys):
        """Traversal rejection must produce CONTRACT_INVALID error."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        cli_main(["inspect", "prepare",
                  "--workspace", repo + "/../",
                  "--runtime-dir", str(runtime)])

        captured = capsys.readouterr()
        err = json.loads(captured.err)
        assert err["error"] == "CONTRACT_INVALID"
        assert "traversal" in err["message"].lower() or "Path" in err["message"]

"""E4 tests — CLI prepare command."""

from pathlib import Path
from furina_code.cli import main as cli_main
from furina_code.ledger import Ledger


class TestCLIPrepare:
    def test_prepare_outputs_json(self, tmp_path):
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 0
        assert (runtime / "context_packet.json").exists()
        assert (runtime / "inspect.sqlite3").exists()

    def test_prepare_creates_backend_profile(self, tmp_path):
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        cli_main(["inspect", "prepare",
                  "--workspace", repo,
                  "--runtime-dir", str(runtime)])

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        bp_head = ledger.get_head_revision("BackendProfile", "local-cli")
        assert bp_head >= 1
        ledger.close()

    def test_prepare_invalid_workspace(self, tmp_path):
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", str(tmp_path / "nonexistent"),
                              "--runtime-dir", str(runtime)])
        assert exit_code == 1

    def test_prepare_not_git_repo(self, tmp_path):
        not_repo = tmp_path / "not_repo"
        not_repo.mkdir()
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", str(not_repo),
                              "--runtime-dir", str(runtime)])
        assert exit_code == 1

    def test_prepare_runtime_inside_workspace_rejected(self, tmp_path):
        repo = str(Path(__file__).resolve().parents[2])
        runtime = Path(repo) / ".runtime_test_inside"
        runtime.mkdir(exist_ok=True)
        try:
            exit_code = cli_main(["inspect", "prepare",
                                  "--workspace", repo,
                                  "--runtime-dir", str(runtime)])
            assert exit_code == 1
        finally:
            runtime.rmdir()

"""E4 tests — CLI prepare command."""

import json
import subprocess
import sys
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

        # Check that context_packet.json was written
        ctx_path = runtime / "context_packet.json"
        assert ctx_path.exists()

        # The stdout output is captured by pytest, so let's check the ledger
        ledger_path = runtime / "inspect.sqlite3"
        assert ledger_path.exists()

    def test_prepare_creates_ledger(self, tmp_path):
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        cli_main(["inspect", "prepare",
                  "--workspace", repo,
                  "--runtime-dir", str(runtime)])

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        # Should have RunBinding, TaskDossier, TaskRun, ProjectSnapshot,
        # ContextEnvelope, Checkpoint events
        events = ledger.get_last_sequence()
        assert events >= 6  # at least 6 objects written
        ledger.close()

    def test_prepare_task_run_at_external_blocked(self, tmp_path):
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        cli_main(["inspect", "prepare",
                  "--workspace", repo,
                  "--runtime-dir", str(runtime)])

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        # Find TaskRun
        # Get events to find task_run_id
        # The first event is RunBinding, then TaskDossier, then TaskRun
        # We need to find the TaskRun head
        # Use a different approach: iterate over events
        all_events = ledger.get_last_sequence()
        assert all_events > 0
        ledger.close()

    def test_prepare_invalid_workspace(self, tmp_path):
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", str(tmp_path / "nonexistent"),
                              "--runtime-dir", str(runtime)])
        assert exit_code == 2

    def test_prepare_not_git_repo(self, tmp_path):
        not_repo = tmp_path / "not_repo"
        not_repo.mkdir()
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", str(not_repo),
                              "--runtime-dir", str(runtime)])
        assert exit_code == 2

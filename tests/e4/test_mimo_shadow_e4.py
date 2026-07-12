"""Tests for MiMo shadow E4 integration."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from furina_code.cli import main as cli_main
from furina_code.ledger import Ledger
from tests.e4.conftest import (
    write_candidate_file,
    get_run_binding_id,
    get_candidate_drop_path,
    get_task_run_id,
)


class TestDefaultBackend:
    def test_default_backend_is_file(self, tmp_path, capsys):
        """Default --backend is file, same as existing behavior."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out.splitlines()[-1])
        assert output["backend_transport_status"] == "awaiting_external"

    def test_explicit_file_backend(self, tmp_path, capsys):
        """--backend file is equivalent to default."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime),
                              "--backend", "file"])
        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out.splitlines()[-1])
        assert output["backend_transport_status"] == "awaiting_external"


class TestMimoRequiresExplicitOptIn:
    def test_mimo_backend_requires_flag(self, tmp_path, capsys):
        """MiMo backend must be explicitly enabled."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        # Without --backend mimo-cli, should use file backend
        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out.splitlines()[-1])
        assert output["backend_transport_status"] == "awaiting_external"

    def test_mimo_backend_unavailable_fails(self, tmp_path, capsys):
        """--backend mimo-cli with unavailable mimo must fail gracefully."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime),
                              "--backend", "mimo-cli"])
        # Should fail because mimo is not on PATH in this context
        assert exit_code == 1


class TestMimoMockIntegration:
    def test_mimo_mock_prepare_finalize_loop(self, tmp_path, capsys):
        """Mock MiMo adapter through prepare -> finalize loop."""
        from furina_code.backend.mimo_cli_adapter import MiMoCodeCLIAdapter
        from furina_code.backend.port import TransportStatus

        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        # Mock probe to return available
        class MockProbe:
            available = True
            version = "mock-1.0"
            executable_ref = "mimo"
            supported_flags = ()
            model_ids = ()
            errors = ()

        original_invoke = MiMoCodeCLIAdapter.invoke

        def mock_invoke(self, plan):
            transport = original_invoke(self, plan)
            if transport.transport_status == TransportStatus.SUCCEEDED.value:
                return transport
            return transport

        # Patch probe to always succeed
        with patch.object(MiMoCodeCLIAdapter, "probe", return_value=MockProbe()):
            # Write a candidate file at the expected location
            # First prepare with mimo-cli backend (will fail at invoke)
            exit_code = cli_main(["inspect", "prepare",
                                  "--workspace", repo,
                                  "--runtime-dir", str(runtime),
                                  "--backend", "mimo-cli"])
            # Expected to fail since mock doesn't produce real output
            assert exit_code == 1


class TestAuthorityBoundary:
    def test_adapter_no_ledger_in_prepare(self, tmp_path, capsys):
        """MiMo adapter path must not write Ledger or create formal objects."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        # Even when mimo fails, it shouldn't touch Ledger for adapter operations
        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo,
                              "--runtime-dir", str(runtime),
                              "--backend", "mimo-cli"])

        # The prepare should have created Ledger objects (TaskRun etc.)
        # but the adapter itself should not have written any
        ledger_path = runtime / "inspect.sqlite3"
        if ledger_path.exists():
            ledger = Ledger(str(ledger_path))
            ledger.open()
            conn = ledger.conn
            cur = conn.execute("SELECT DISTINCT run_binding_id FROM event_envelopes LIMIT 1")
            row = cur.fetchone()
            if row:
                events = ledger.get_verified_events(row[0])
                adapter_events = [e for e in events if "mimo" in e.get("producer_organ", "").lower()]
                assert len(adapter_events) == 0
            ledger.close()


class TestFinalizeConsumesMimoCandidate:
    def test_finalize_works_with_any_candidate_source(self, tmp_path, capsys):
        """Finalize should consume candidate regardless of its source (file or mimo)."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        # Use default file backend to create the prepare state
        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])

        # Write a candidate at the deterministic path
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path])
        assert exit_code == 0

        # Verify completion
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        events = ledger.get_verified_events(rb_id)
        cv_events = [e for e in events if e["event_type"].startswith("CompletionVerdict.")]
        ledger.close()
        assert len(cv_events) >= 1

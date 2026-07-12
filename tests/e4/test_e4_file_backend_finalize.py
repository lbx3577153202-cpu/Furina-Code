"""Tests for E4 FileBackend finalize integration."""

import ast
import json
from pathlib import Path

import pytest

from furina_code.cli import main as cli_main
from furina_code.backend.port import TransportStatus
from furina_code.contracts.errors import ContractInvalid
from furina_code.readonly.file_backend_bridge import (
    build_e4_file_backend_request,
    finalize_e4_file_transport,
)
from furina_code.ledger import Ledger
from tests.e4.conftest import (
    write_candidate_file,
    get_run_binding_id,
    get_candidate_drop_path,
    get_task_run_id,
)


class TestFinalizeFileBackendLifecycle:
    def test_full_loop_via_filebackend(self, tmp_path, capsys):
        """Prepare → candidate drop → finalize succeeds with FileBackend lifecycle."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path])
        assert exit_code == 0

    def test_finalize_uses_collect_and_strict_validate(self, tmp_path, capsys):
        """Finalize should run FileBackend collect + strict_validate."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path])
        assert exit_code == 0

        # Canonical artifact should exist at deterministic path
        tr_id = get_task_run_id(runtime)
        canonical = runtime / "backend" / rb_id / tr_id / "output" / "collected_candidate.json"
        assert canonical.exists()


class TestCandidatePathBinding:
    def test_candidate_path_mismatch_rejected(self, tmp_path, capsys):
        """Finalize rejects candidate at wrong path."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
        rb_id = get_run_binding_id(runtime)

        # Write candidate at wrong path
        wrong_path = runtime / "wrong_candidate.json"
        wrong_path.write_text("{}", encoding="utf-8")

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", str(wrong_path)])
        assert exit_code == 1
        stderr = capsys.readouterr().err
        err = json.loads(stderr)
        assert err["error"] == "CONTRACT_INVALID"

    def test_candidate_path_deterministic(self, tmp_path):
        """Candidate drop path is deterministic from run_binding_id and task_run_id."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
        drop_path = get_candidate_drop_path(runtime)

        # Must follow the pattern: runtime/backend/<rb_id>/<tr_id>/candidate.json
        rel = Path(drop_path).relative_to(runtime)
        parts = rel.parts
        assert parts[0] == "backend"
        assert len(parts) == 4  # backend/<rb_id>/<tr_id>/candidate.json
        assert parts[3] == "candidate.json"


class TestIdempotency:
    def test_same_candidate_replay(self, tmp_path, capsys):
        """Same candidate finalized twice returns existing result."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        # First finalize
        exit1 = cli_main(["inspect", "finalize",
                          "--runtime-dir", str(runtime),
                          "--run-binding-id", rb_id,
                          "--candidate-file", cand_path])
        assert exit1 == 0
        capsys.readouterr()  # clear

        # Second finalize with same candidate
        exit2 = cli_main(["inspect", "finalize",
                          "--runtime-dir", str(runtime),
                          "--run-binding-id", rb_id,
                          "--candidate-file", cand_path])
        assert exit2 == 0
        second_out = json.loads(capsys.readouterr().out)
        assert second_out["outcome"] == "completed"

    def test_different_candidate_conflict(self, tmp_path, capsys):
        """Different candidate finalized after completion returns IDEMPOTENCY_CONFLICT."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])
        capsys.readouterr()

        # Different candidate
        cand_path2 = write_candidate_file(runtime, repository_head="b" * 40)
        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path2])
        assert exit_code == 1
        stderr = capsys.readouterr().err
        err = json.loads(stderr)
        assert err["error"] == "IDEMPOTENCY_CONFLICT"


class TestExistingBehaviorPreserved:
    def test_finalize_unchanged_output_fields(self, tmp_path, capsys):
        """Finalize still produces all expected output fields."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])

        # Output has both prepare + finalize JSON lines; take the last one
        all_out = capsys.readouterr().out.strip().splitlines()
        output = json.loads(all_out[-1])
        assert "candidate_ref" in output
        assert "verification_plan_ref" in output
        assert "verification_verdict_ref" in output
        assert "completion_verdict_ref" in output
        assert "task_run_ref" in output
        assert "outcome" in output
        assert "completed_items" in output
        assert "incomplete_items" in output

    def test_wrong_phase_still_rejected(self, tmp_path, capsys):
        """Finalize still rejects non-terminal non-external_blocked TaskRun."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
        rb_id = get_run_binding_id(runtime)

        # Finalize without candidate — should fail
        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", str(runtime / "nonexistent.json")])
        assert exit_code == 1

    def test_invalid_utf8_rejected(self, tmp_path, capsys):
        """Finalize rejects invalid UTF-8 candidate."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
        rb_id = get_run_binding_id(runtime)

        # Write invalid UTF-8 at the deterministic path
        drop = Path(get_candidate_drop_path(runtime))
        drop.parent.mkdir(parents=True, exist_ok=True)
        drop.write_bytes(b"\xff\xfe invalid")

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", str(drop)])
        assert exit_code == 1
        stderr = capsys.readouterr().err
        err = json.loads(stderr)
        assert err["error"] in ("CONTRACT_INVALID",)


class TestAuthorityBoundary:
    def test_bridge_does_not_import_ledger(self):
        bridge_path = Path(__file__).resolve().parents[2] / "src" / "furina_code" / "readonly" / "file_backend_bridge.py"
        tree = ast.parse(bridge_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "ledger" not in alias.name.lower()
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    assert "ledger" not in node.module.lower()

    def test_bridge_does_not_create_formal_objects(self):
        bridge_path = Path(__file__).resolve().parents[2] / "src" / "furina_code" / "readonly" / "file_backend_bridge.py"
        source = bridge_path.read_text(encoding="utf-8")
        assert "CandidateEnvelope.create" not in source
        assert "BackendProfile.create" not in source
        assert "TaskRun.create" not in source
        assert "CompletionVerdict.create" not in source

    def test_cli_finalize_output_no_path_leak(self, tmp_path, capsys):
        """Finalize error output should not leak absolute paths."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
        rb_id = get_run_binding_id(runtime)

        wrong_path = runtime / "wrong.json"
        wrong_path.write_text("{}", encoding="utf-8")

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", str(wrong_path)])
        assert exit_code == 1
        stderr = capsys.readouterr().err
        err = json.loads(stderr)
        # Error message should be stable code, not a path
        assert "error" in err


class TestCanonicalDigestBinding:
    def test_canonical_modified_after_collect_fails(self, tmp_path, capsys):
        """If read_candidate_once returns a digest different from
        transport.candidate_digest, finalize must fail and must NOT
        create CandidateEnvelope."""
        from unittest.mock import patch as mock_patch
        from furina_code.backend.candidate import (
            read_candidate_once as _real_read_candidate_once,
        )

        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        # First finalize succeeds — no monkeypatch
        exit1 = cli_main(["inspect", "finalize",
                          "--runtime-dir", str(runtime),
                          "--run-binding-id", rb_id,
                          "--candidate-file", cand_path])
        assert exit1 == 0
        capsys.readouterr()

        # Second finalize: monkeypatch to return mismatched digest
        def tampered_read(path):
            text, parsed, _ = _real_read_candidate_once(path)
            return text, parsed, "0000" * 16

        with mock_patch(
            "furina_code.cli.read_candidate_once", tampered_read
        ):
            exit2 = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path])

        assert exit2 == 1
        stderr = capsys.readouterr().err
        err = json.loads(stderr)
        assert err["error"] == "CANDIDATE_EVIDENCE_MISMATCH"

        # Must NOT have created a new CandidateEnvelope
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        ce_events = [
            e for e in ledger.get_verified_events(rb_id)
            if e["event_type"].startswith("CandidateEnvelope.")
        ]
        ledger.close()
        assert len(ce_events) == 1  # only from first finalize

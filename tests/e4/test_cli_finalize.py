"""E4 tests — CLI finalize command."""

import json
import pytest
from pathlib import Path
from furina_code.cli import main as cli_main
from furina_code.ledger import Ledger


def _prepare(tmp_path):
    """Helper: run prepare and return runtime dir path."""
    repo = str(Path(__file__).resolve().parents[2])
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cli_main(["inspect", "prepare",
              "--workspace", repo,
              "--runtime-dir", str(runtime)])
    return runtime


def _write_good_candidate(runtime, context_ref="sha256:placeholder"):
    """Write a valid candidate JSON file."""
    # Read the context packet to get the real context_envelope_ref
    ctx_path = runtime / "context_packet.json"
    ctx_data = json.loads(ctx_path.read_text(encoding="utf-8"))
    real_ctx_ref = ctx_data["context_envelope_ref"]

    # Read the snapshot from the context
    snap = ctx_data.get("context_payload", {}).get("snapshot_summary", {})

    candidate = {
        "schema_version": "1.0",
        "candidate_type": "repository_baseline_report",
        "backend_profile_ref": "e4-repository-baseline-v1",
        "backend_session_ref": "session-1",
        "context_ref": real_ctx_ref,
        "context_digest": ctx_data.get("context_digest", "sha256:0"),
        "content": {
            "repository_head": snap.get("head_sha", "a" * 40),
            "branch": snap.get("branch", "main"),
            "working_tree": "clean" if snap.get("is_clean", True) else "dirty",
            "tracked_file_count": snap.get("tracked_file_count", 0),
            "untracked_file_count": snap.get("untracked_file_count", 0),
            "python_requires": snap.get("requires_python"),
            "runtime_dependencies": snap.get("runtime_dependencies", []),
            "dev_dependencies": snap.get("dev_dependencies", []),
            "pytest_testpaths": snap.get("pytest_testpaths", []),
            "ci_config": {
                "present": snap.get("ci_config_exists", False),
                "sha256": snap.get("ci_config_sha256"),
            },
            "blind_spots": snap.get("blind_spots", []),
            "summary": "Automated baseline report",
        },
        "claimed_assumptions": [],
        "requested_actions": [],
    }
    cand_path = runtime / "candidate.json"
    cand_path.write_text(json.dumps(candidate), encoding="utf-8")
    return str(cand_path)


def _get_run_binding_id(runtime):
    """Extract run_binding_id from the ledger."""
    ledger = Ledger(str(runtime / "inspect.sqlite3"))
    ledger.open()
    # Get the first event which is RunBinding.created
    # The run_binding_id is in the event's aggregate_ref
    # Actually, let's just get it from the context packet
    ctx_path = runtime / "context_packet.json"
    ctx_data = json.loads(ctx_path.read_text(encoding="utf-8"))
    # The run_binding_id isn't in the context packet directly
    # Let's find it from the ledger RunBinding objects
    # The first event has the run_binding_id in run_binding_id column
    events = ledger.get_last_sequence()
    # Get all events for any binding
    conn = ledger.conn
    cur = conn.execute("SELECT DISTINCT run_binding_id FROM event_envelopes LIMIT 1")
    row = cur.fetchone()
    rb_id = row[0] if row else None
    ledger.close()
    return rb_id


class TestCLIFinalize:
    def test_finalize_outputs_json(self, tmp_path):
        runtime = _prepare(tmp_path)
        cand_path = _write_good_candidate(runtime)
        rb_id = _get_run_binding_id(runtime)

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path])
        assert exit_code == 0

    def test_finalize_pass_candidate(self, tmp_path):
        runtime = _prepare(tmp_path)
        cand_path = _write_good_candidate(runtime)
        rb_id = _get_run_binding_id(runtime)

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path])
        assert exit_code == 0

    def test_finalize_missing_ledger(self, tmp_path):
        runtime = tmp_path / "empty_runtime"
        runtime.mkdir()
        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", "rb-1",
                              "--candidate-file", "dummy.json"])
        assert exit_code == 2

    def test_finalize_missing_candidate(self, tmp_path):
        runtime = _prepare(tmp_path)
        rb_id = _get_run_binding_id(runtime)

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", str(tmp_path / "nonexistent.json")])
        assert exit_code == 1

    def test_finalize_task_run_terminal(self, tmp_path):
        runtime = _prepare(tmp_path)
        cand_path = _write_good_candidate(runtime)
        rb_id = _get_run_binding_id(runtime)

        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])

        # Verify TaskRun reached terminal
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        conn = ledger.conn
        cur = conn.execute(
            "SELECT current_revision FROM object_heads WHERE object_type='TaskRun'"
        )
        row = cur.fetchone()
        assert row is not None
        rev = row[0]
        result = ledger.get_latest("TaskRun", list(
            conn.execute("SELECT object_id FROM object_heads WHERE object_type='TaskRun'").fetchone()
            or [None]
        )[0] or "")
        if result:
            _, payload = result
            assert payload["phase"] == "terminal"
            assert payload["disposition"] == "terminal"
        ledger.close()

    def test_finalize_creates_all_objects(self, tmp_path):
        runtime = _prepare(tmp_path)
        cand_path = _write_good_candidate(runtime)
        rb_id = _get_run_binding_id(runtime)

        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        conn = ledger.conn
        cur = conn.execute("SELECT DISTINCT object_type FROM object_revisions")
        types = {row[0] for row in cur.fetchall()}
        assert "CandidateEnvelope" in types
        assert "EvidenceEnvelope" in types
        assert "VerificationPlan" in types
        assert "VerificationVerdict" in types
        assert "CompletionVerdict" in types
        ledger.close()

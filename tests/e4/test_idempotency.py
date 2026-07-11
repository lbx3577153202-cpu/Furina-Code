"""E4 tests — idempotency and restart."""

import json
from pathlib import Path
from furina_code.cli import main as cli_main
from furina_code.ledger import Ledger


def _prepare(tmp_path):
    repo = str(Path(__file__).resolve().parents[2])
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
    return runtime


def _get_rb_id(runtime):
    ledger = Ledger(str(runtime / "inspect.sqlite3"))
    ledger.open()
    conn = ledger.conn
    cur = conn.execute("SELECT DISTINCT run_binding_id FROM event_envelopes LIMIT 1")
    row = cur.fetchone()
    ledger.close()
    return row[0] if row else None


def _write_good_candidate(runtime):
    ctx_path = runtime / "context_packet.json"
    ctx_data = json.loads(ctx_path.read_text(encoding="utf-8"))
    snap = ctx_data.get("context_payload", {}).get("snapshot_summary", {})

    candidate = {
        "schema_version": "1.0",
        "candidate_type": "repository_baseline_report",
        "backend_profile_ref": "e4-repository-baseline-v1",
        "backend_session_ref": "session-1",
        "context_ref": ctx_data["context_envelope_ref"],
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
            "summary": "test",
        },
        "claimed_assumptions": [],
        "requested_actions": [],
    }
    cand_path = runtime / "candidate.json"
    cand_path.write_text(json.dumps(candidate), encoding="utf-8")
    return str(cand_path)


class TestIdempotency:
    def test_same_candidate_replay(self, tmp_path):
        """Finalize with the same candidate twice — second should fail
        because TaskRun is already terminal."""
        runtime = _prepare(tmp_path)
        cand_path = _write_good_candidate(runtime)
        rb_id = _get_rb_id(runtime)

        # First finalize
        exit1 = cli_main(["inspect", "finalize",
                          "--runtime-dir", str(runtime),
                          "--run-binding-id", rb_id,
                          "--candidate-file", cand_path])
        assert exit1 == 0

        # Second finalize with same candidate — TaskRun is terminal now
        exit2 = cli_main(["inspect", "finalize",
                          "--runtime-dir", str(runtime),
                          "--run-binding-id", rb_id,
                          "--candidate-file", cand_path])
        # Should fail because TaskRun is terminal, not external_blocked
        assert exit2 != 0

    def test_restart_between_prepare_finalize(self, tmp_path):
        """Simulate restart: prepare creates ledger, close process,
        then finalize reads ledger and completes."""
        runtime = _prepare(tmp_path)
        cand_path = _write_good_candidate(runtime)
        rb_id = _get_rb_id(runtime)

        # "Restart" — just call finalize directly (ledger is on disk)
        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path])
        assert exit_code == 0

        # Verify terminal state
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        conn = ledger.conn
        cur = conn.execute(
            "SELECT object_id FROM object_heads WHERE object_type='TaskRun'"
        )
        tr_id = cur.fetchone()[0]
        result = ledger.get_latest("TaskRun", tr_id)
        assert result is not None
        _, payload = result
        assert payload["phase"] == "terminal"
        assert payload["disposition"] == "terminal"
        ledger.close()

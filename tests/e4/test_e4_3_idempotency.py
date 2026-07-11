"""E4.3 tests — idempotency, different candidate conflict, and invalid-then-corrected."""

import json
from pathlib import Path
from furina_code.cli import main as cli_main
from furina_code.ledger import Ledger
from furina_code.contracts.errors import ContractInvalid
from tests.e4.conftest import write_candidate_file, get_run_binding_id, get_context_digest


def _prepare(tmp_path):
    repo = str(Path(__file__).resolve().parents[2])
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
    return runtime


class TestE43Idempotency:
    def test_same_candidate_replay_outputs_equal(self, tmp_path, capsys):
        """Same candidate replay must produce identical JSON output."""
        runtime = _prepare(tmp_path)
        # Drain prepare output
        capsys.readouterr()

        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        # First finalize
        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])
        captured1 = capsys.readouterr()
        out1 = json.loads(captured1.out)

        # Replay same candidate
        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])
        captured2 = capsys.readouterr()
        out2 = json.loads(captured2.out)

        # Compare key fields
        assert out1["candidate_ref"] == out2["candidate_ref"]
        assert out1["completion_verdict_ref"] == out2["completion_verdict_ref"]
        assert out1["outcome"] == out2["outcome"]
        assert out1["completed_items"] == out2["completed_items"]

    def test_same_candidate_events_unchanged(self, tmp_path):
        """Same candidate replay must not create new events."""
        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        # First finalize
        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        events_after_first = ledger.get_last_sequence()
        ledger.close()

        # Replay
        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        events_after_second = ledger.get_last_sequence()
        ledger.close()

        assert events_after_first == events_after_second

    def test_same_candidate_revisions_unchanged(self, tmp_path):
        """Same candidate replay must not change object revisions."""
        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        # First finalize
        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        heads_first = {}
        cur = ledger.conn.execute("SELECT object_type, object_id, current_revision FROM object_heads")
        for row in cur.fetchall():
            heads_first[(row[0], row[1])] = row[2]
        ledger.close()

        # Replay
        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        heads_second = {}
        cur = ledger.conn.execute("SELECT object_type, object_id, current_revision FROM object_heads")
        for row in cur.fetchall():
            heads_second[(row[0], row[1])] = row[2]
        ledger.close()

        assert heads_first == heads_second

    def test_different_candidate_conflict(self, tmp_path):
        """Different candidate for completed run must return IDEMPOTENCY_CONFLICT."""
        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        # First finalize
        exit1 = cli_main(["inspect", "finalize",
                          "--runtime-dir", str(runtime),
                          "--run-binding-id", rb_id,
                          "--candidate-file", cand_path])
        assert exit1 == 0

        # Different candidate (different HEAD)
        cand_path2 = write_candidate_file(runtime, repository_head="b" * 40)
        exit2 = cli_main(["inspect", "finalize",
                          "--runtime-dir", str(runtime),
                          "--run-binding-id", rb_id,
                          "--candidate-file", cand_path2])
        assert exit2 == 1

    def test_different_candidate_no_mutation(self, tmp_path):
        """Different candidate conflict must not mutate events or revisions."""
        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        # First finalize
        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        events_before = ledger.get_last_sequence()
        heads_before = {}
        cur = ledger.conn.execute("SELECT object_type, object_id, current_revision FROM object_heads")
        for row in cur.fetchall():
            heads_before[(row[0], row[1])] = row[2]
        ledger.close()

        # Different candidate
        cand_path2 = write_candidate_file(runtime, repository_head="b" * 40)
        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path2])

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        events_after = ledger.get_last_sequence()
        heads_after = {}
        cur = ledger.conn.execute("SELECT object_type, object_id, current_revision FROM object_heads")
        for row in cur.fetchall():
            heads_after[(row[0], row[1])] = row[2]
        ledger.close()

        assert events_before == events_after
        assert heads_before == heads_after

    def test_invalid_then_corrected(self, tmp_path, capsys):
        """Invalid candidate followed by valid candidate must succeed."""
        runtime = _prepare(tmp_path)
        rb_id = get_run_binding_id(runtime)

        # Write invalid candidate (wrong context digest)
        ctx_path = runtime / "context_packet.json"
        ctx_data = json.loads(ctx_path.read_text(encoding="utf-8"))
        invalid_cand = {
            "schema_version": "1.0",
            "candidate_type": "repository_baseline_report",
            "backend_profile_ref": "e4-repository-baseline-v1",
            "backend_session_ref": "test-session",
            "context_ref": ctx_data["context_envelope_ref"],
            "context_digest": "sha256:wrong_digest",
            "content": {
                "repository_head": "a" * 40,
                "branch": "main",
                "working_tree": "clean",
                "tracked_file_count": 0,
                "untracked_file_count": 0,
                "python_requires": None,
                "runtime_dependencies": [],
                "dev_dependencies": [],
                "pytest_testpaths": [],
                "ci_config": {"present": False, "sha256": None},
                "blind_spots": [],
            },
            "claimed_assumptions": [],
            "requested_actions": [],
        }
        invalid_path = tmp_path / "invalid.json"
        invalid_path.write_text(json.dumps(invalid_cand))

        # First finalize with invalid candidate
        exit1 = cli_main(["inspect", "finalize",
                          "--runtime-dir", str(runtime),
                          "--run-binding-id", rb_id,
                          "--candidate-file", str(invalid_path)])
        assert exit1 == 1

        # Verify no CandidateEnvelope was created
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        ce_events = [e for e in ledger.get_verified_events(rb_id)
                     if e["event_type"].startswith("CandidateEnvelope.")]
        assert len(ce_events) == 0

        # Verify TaskRun is still deliberate/external_blocked
        tr_events = [e for e in ledger.get_verified_events(rb_id)
                     if e["event_type"].startswith("TaskRun.")]
        tr_ref = tr_events[-1]["aggregate_ref"]
        tr_obj_id = tr_ref.split(":", 1)[1]
        _, tr_payload = ledger.get_latest("TaskRun", tr_obj_id)
        assert tr_payload["phase"] == "deliberate"
        assert tr_payload["disposition"] == "external_blocked"
        ledger.close()

        # Now finalize with valid candidate
        cand_path = write_candidate_file(runtime)
        exit2 = cli_main(["inspect", "finalize",
                          "--runtime-dir", str(runtime),
                          "--run-binding-id", rb_id,
                          "--candidate-file", cand_path])
        assert exit2 == 0

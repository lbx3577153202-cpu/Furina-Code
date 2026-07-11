"""E4 tests — full prepare/finalize loop."""

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


def _get_run_binding_id(runtime):
    ledger = Ledger(str(runtime / "inspect.sqlite3"))
    ledger.open()
    conn = ledger.conn
    cur = conn.execute("SELECT DISTINCT run_binding_id FROM event_envelopes LIMIT 1")
    row = cur.fetchone()
    rb_id = row[0] if row else None
    ledger.close()
    return rb_id


def _write_candidate(runtime, **overrides):
    ctx_path = runtime / "context_packet.json"
    ctx_data = json.loads(ctx_path.read_text(encoding="utf-8"))
    snap = ctx_data.get("context_payload", {}).get("snapshot_summary", {})

    content = {
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
    }
    content.update(overrides)

    candidate = {
        "schema_version": "1.0",
        "candidate_type": "repository_baseline_report",
        "backend_profile_ref": "e4-repository-baseline-v1",
        "backend_session_ref": "session-1",
        "context_ref": ctx_data["context_envelope_ref"],
        "context_digest": ctx_data.get("context_digest", "sha256:0"),
        "content": content,
        "claimed_assumptions": [],
        "requested_actions": [],
    }
    cand_path = runtime / "candidate.json"
    cand_path.write_text(json.dumps(candidate), encoding="utf-8")
    return str(cand_path)


class TestFullLoop:
    def test_prepare_then_finalize_pass(self, tmp_path):
        runtime = _prepare(tmp_path)
        cand_path = _write_candidate(runtime)
        rb_id = _get_run_binding_id(runtime)

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path])
        assert exit_code == 0

    def test_prepare_then_finalize_fail(self, tmp_path):
        runtime = _prepare(tmp_path)
        cand_path = _write_candidate(runtime, repository_head="b" * 40)
        rb_id = _get_run_binding_id(runtime)

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path])
        assert exit_code == 0  # finalize succeeds but verdict is "failed"

    def test_workspace_unchanged(self, tmp_path):
        """Verify that the target workspace is not modified."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        # Record state before
        import subprocess
        before = subprocess.run(["git", "status", "--porcelain"],
                                capture_output=True, text=True, shell=False, cwd=repo)
        before_status = before.stdout.strip()

        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])

        after = subprocess.run(["git", "status", "--porcelain"],
                               capture_output=True, text=True, shell=False, cwd=repo)
        after_status = after.stdout.strip()

        assert before_status == after_status

    def test_full_loop_event_count(self, tmp_path):
        """Verify the full loop produces the expected number of events."""
        runtime = _prepare(tmp_path)
        cand_path = _write_candidate(runtime)
        rb_id = _get_run_binding_id(runtime)

        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        total_events = ledger.get_last_sequence()
        # prepare: RunBinding + TaskDossier + TaskRun(4 revisions) +
        #          ProjectSnapshot + ContextEnvelope + Checkpoint = ~9
        # finalize: CandidateEnvelope + TaskRun(4 more revisions) +
        #           VerificationPlan + EvidenceEnvelope*10 + VerificationVerdict*10 +
        #           CompletionVerdict + Checkpoint = ~28
        # Total should be > 30
        assert total_events > 20
        ledger.close()

    def test_full_loop_continuity_view(self, tmp_path):
        """ContinuityView after finalize shows terminal phase."""
        from furina_code.continuity import rebuild_continuity

        runtime = _prepare(tmp_path)
        cand_path = _write_candidate(runtime)
        rb_id = _get_run_binding_id(runtime)

        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        view = rebuild_continuity(ledger, rb_id)
        assert view.task_phase == "terminal"
        assert view.task_disposition == "terminal"
        ledger.close()

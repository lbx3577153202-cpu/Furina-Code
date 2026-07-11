"""E4 tests — CLI finalize command."""

import json
from pathlib import Path
from furina_code.cli import main as cli_main
from furina_code.ledger import Ledger
from tests.e4.conftest import write_candidate_file, get_run_binding_id


def _prepare(tmp_path):
    repo = str(Path(__file__).resolve().parents[2])
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cli_main(["inspect", "prepare",
              "--workspace", repo,
              "--runtime-dir", str(runtime)])
    return runtime


class TestCLIFinalize:
    def test_finalize_outputs_json(self, tmp_path):
        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path])
        assert exit_code == 0

    def test_finalize_pass_candidate(self, tmp_path):
        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

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
        rb_id = get_run_binding_id(runtime)

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", str(tmp_path / "nonexistent.json")])
        assert exit_code == 1

    def test_finalize_task_run_terminal(self, tmp_path):
        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        conn = ledger.conn
        cur = conn.execute("SELECT object_id FROM object_heads WHERE object_type='TaskRun' LIMIT 1")
        tr_id = cur.fetchone()[0]
        result = ledger.get_latest("TaskRun", tr_id)
        assert result is not None
        _, payload = result
        assert payload["phase"] == "terminal"
        assert payload["disposition"] == "terminal"
        ledger.close()

    def test_finalize_creates_all_objects(self, tmp_path):
        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

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

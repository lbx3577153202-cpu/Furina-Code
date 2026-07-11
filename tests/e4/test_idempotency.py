"""E4 tests — idempotency and restart."""

from pathlib import Path
from furina_code.cli import main as cli_main
from furina_code.ledger import Ledger
from tests.e4.conftest import write_candidate_file, get_run_binding_id


def _prepare(tmp_path):
    repo = str(Path(__file__).resolve().parents[2])
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
    return runtime


class TestIdempotency:
    def test_same_candidate_replay(self, tmp_path):
        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        exit1 = cli_main(["inspect", "finalize",
                          "--runtime-dir", str(runtime),
                          "--run-binding-id", rb_id,
                          "--candidate-file", cand_path])
        assert exit1 == 0

        # Replay same candidate
        exit2 = cli_main(["inspect", "finalize",
                          "--runtime-dir", str(runtime),
                          "--run-binding-id", rb_id,
                          "--candidate-file", cand_path])
        assert exit2 == 0  # idempotent

    def test_restart_between_prepare_finalize(self, tmp_path):
        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path])
        assert exit_code == 0

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        conn = ledger.conn
        cur = conn.execute(
            "SELECT object_id FROM object_heads WHERE object_type='TaskRun' LIMIT 1"
        )
        tr_id = cur.fetchone()[0]
        result = ledger.get_latest("TaskRun", tr_id)
        assert result is not None
        _, payload = result
        assert payload["phase"] == "terminal"
        ledger.close()

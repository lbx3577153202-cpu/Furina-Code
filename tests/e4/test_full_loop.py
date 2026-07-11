"""E4 tests — full prepare/finalize loop."""

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


class TestFullLoop:
    def test_prepare_then_finalize_pass(self, tmp_path):
        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path])
        assert exit_code == 0

    def test_prepare_then_finalize_fail(self, tmp_path):
        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime, repository_head="b" * 40)
        rb_id = get_run_binding_id(runtime)

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", cand_path])
        assert exit_code == 0

    def test_workspace_unchanged(self, tmp_path):
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        import subprocess
        before = subprocess.run(["git", "status", "--porcelain=v2"],
                                capture_output=True, text=True, shell=False, cwd=repo)

        cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])

        after = subprocess.run(["git", "status", "--porcelain=v2"],
                               capture_output=True, text=True, shell=False, cwd=repo)

        assert before.stdout == after.stdout

    def test_full_loop_event_count(self, tmp_path):
        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        total_events = ledger.get_last_sequence()
        assert total_events > 20
        ledger.close()

    def test_full_loop_continuity_view(self, tmp_path):
        from furina_code.continuity import rebuild_continuity

        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

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

    def test_task_run_skips_authorize_act_reconcile(self, tmp_path):
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
        cur = conn.execute("SELECT DISTINCT object_id FROM object_heads WHERE object_type='TaskRun'")
        for row in cur.fetchall():
            result = ledger.get_latest("TaskRun", row[0])
            if result:
                _, p = result
                assert p["phase"] not in ("authorize", "act", "reconcile")
        ledger.close()

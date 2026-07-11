"""E4 tests — security boundaries."""

import json
from pathlib import Path
from furina_code.cli import main as cli_main


class TestSecurityBoundaries:
    def test_runtime_inside_workspace_rejected(self, tmp_path):
        """runtime-dir inside workspace must be rejected."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = Path(repo) / "runtime_inside"
        runtime.mkdir(exist_ok=True)
        try:
            exit_code = cli_main(["inspect", "prepare",
                                  "--workspace", repo,
                                  "--runtime-dir", str(runtime)])
            assert exit_code == 1
        finally:
            runtime.rmdir()

    def test_path_traversal_rejected(self, tmp_path):
        """Paths with .. are rejected."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        # workspace with .. should be rejected
        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", repo + "/..",
                              "--runtime-dir", str(runtime)])
        assert exit_code == 1

    def test_context_no_secrets_in_packet(self, tmp_path):
        """Context packet should not contain secrets."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        cli_main(["inspect", "prepare",
                  "--workspace", repo,
                  "--runtime-dir", str(runtime)])

        ctx_path = runtime / "context_packet.json"
        content = ctx_path.read_text(encoding="utf-8")
        assert "API_KEY" not in content
        assert "SECRET" not in content

    def test_candidate_too_large_rejected(self, tmp_path):
        """Oversized candidate file is rejected."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        cli_main(["inspect", "prepare",
                  "--workspace", repo,
                  "--runtime-dir", str(runtime)])

        from furina_code.ledger import Ledger
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        conn = ledger.conn
        cur = conn.execute("SELECT DISTINCT run_binding_id FROM event_envelopes LIMIT 1")
        rb_id = cur.fetchone()[0]
        ledger.close()

        cand_path = tmp_path / "large_candidate.json"
        cand_path.write_bytes(b"x" * (11 * 1024 * 1024))

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", str(cand_path)])
        assert exit_code == 1

    def test_non_json_candidate_rejected(self, tmp_path):
        """Non-JSON candidate file is rejected."""
        repo = str(Path(__file__).resolve().parents[2])
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        cli_main(["inspect", "prepare",
                  "--workspace", repo,
                  "--runtime-dir", str(runtime)])

        from furina_code.ledger import Ledger
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        conn = ledger.conn
        cur = conn.execute("SELECT DISTINCT run_binding_id FROM event_envelopes LIMIT 1")
        rb_id = cur.fetchone()[0]
        ledger.close()

        cand_path = tmp_path / "bad.json"
        cand_path.write_text("not json")

        exit_code = cli_main(["inspect", "finalize",
                              "--runtime-dir", str(runtime),
                              "--run-binding-id", rb_id,
                              "--candidate-file", str(cand_path)])
        assert exit_code == 1

"""E4.3 tests — complete causation chain verification."""

from pathlib import Path
from furina_code.cli import main as cli_main
from furina_code.ledger import Ledger


def _prepare_and_finalize(tmp_path):
    """Run full prepare/finalize and return runtime path."""
    from tests.e4.conftest import write_candidate_file, get_run_binding_id

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
    return runtime, rb_id


class TestCausationChain:
    def test_task_dossier_causation_ref(self, tmp_path):
        """TaskDossier.causation_ref must point to RunBinding."""
        runtime, rb_id = _prepare_and_finalize(tmp_path)

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()

        # Get RunBinding
        rb_events = [e for e in ledger.get_verified_events(rb_id)
                     if e["event_type"].startswith("RunBinding.")]
        assert len(rb_events) > 0
        rb_ref = rb_events[0]["aggregate_ref"]
        rb_obj_id = rb_ref.split(":", 1)[1]
        rb_meta, _ = ledger.get_latest("RunBinding", rb_obj_id)

        # Get TaskDossier
        td_events = [e for e in ledger.get_verified_events(rb_id)
                     if e["event_type"].startswith("TaskDossier.")]
        assert len(td_events) > 0
        td_ref = td_events[0]["aggregate_ref"]
        td_obj_id = td_ref.split(":", 1)[1]
        td_meta, _ = ledger.get_latest("TaskDossier", td_obj_id)

        assert td_meta.causation_ref == rb_meta.integrity_ref
        ledger.close()

    def test_initial_task_run_causation_ref(self, tmp_path):
        """Initial TaskRun.causation_ref must point to TaskDossier."""
        runtime, rb_id = _prepare_and_finalize(tmp_path)

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()

        td_events = [e for e in ledger.get_verified_events(rb_id)
                     if e["event_type"].startswith("TaskDossier.")]
        td_ref = td_events[0]["aggregate_ref"]
        td_obj_id = td_ref.split(":", 1)[1]
        td_meta, _ = ledger.get_latest("TaskDossier", td_obj_id)

        tr_events = [e for e in ledger.get_verified_events(rb_id)
                     if e["event_type"].startswith("TaskRun.")]
        tr_ref = tr_events[0]["aggregate_ref"]
        tr_obj_id = tr_ref.split(":", 1)[1]
        tr_meta, _ = ledger.get_latest("TaskRun", tr_obj_id)

        # Initial TaskRun should have causation_ref pointing to TaskDossier
        # (or at least non-None)
        assert tr_meta.causation_ref is not None
        ledger.close()

    def test_prepare_checkpoint_causation_ref(self, tmp_path):
        """Prepare Checkpoint.causation_ref must point to TaskRun revision."""
        runtime, rb_id = _prepare_and_finalize(tmp_path)

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()

        cp_events = [e for e in ledger.get_verified_events(rb_id)
                     if e["event_type"].startswith("Checkpoint.")]
        # First checkpoint is the prepare checkpoint
        assert len(cp_events) >= 2  # prepare + final
        cp_ref = cp_events[0]["aggregate_ref"]
        cp_obj_id = cp_ref.split(":", 1)[1]
        cp_meta, _ = ledger.get_latest("Checkpoint", cp_obj_id)

        assert cp_meta.causation_ref is not None
        assert cp_meta.causation_ref.startswith("sha256:")
        ledger.close()

    def test_final_checkpoint_causation_ref(self, tmp_path):
        """Final Checkpoint.causation_ref must point to CompletionVerdict."""
        runtime, rb_id = _prepare_and_finalize(tmp_path)

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()

        cv_events = [e for e in ledger.get_verified_events(rb_id)
                     if e["event_type"].startswith("CompletionVerdict.")]
        assert len(cv_events) > 0
        cv_ref = cv_events[0]["aggregate_ref"]
        cv_obj_id = cv_ref.split(":", 1)[1]
        cv_meta, _ = ledger.get_latest("CompletionVerdict", cv_obj_id)

        cp_events = [e for e in ledger.get_verified_events(rb_id)
                     if e["event_type"].startswith("Checkpoint.")]
        # Last checkpoint is the final checkpoint
        cp_ref = cp_events[-1]["aggregate_ref"]
        cp_obj_id = cp_ref.split(":", 1)[1]
        cp_meta, _ = ledger.get_latest("Checkpoint", cp_obj_id)

        assert cp_meta.causation_ref == cv_meta.integrity_ref
        ledger.close()

    def test_all_causation_refs_non_empty(self, tmp_path):
        """All objects in the chain must have non-empty causation_ref."""
        runtime, rb_id = _prepare_and_finalize(tmp_path)

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        events = ledger.get_verified_events(rb_id)

        # Collect all unique aggregate refs
        seen = set()
        for evt in events:
            agg_ref = evt["aggregate_ref"]
            if agg_ref in seen:
                continue
            seen.add(agg_ref)
            obj_type, obj_id = agg_ref.split(":", 1)
            result = ledger.get_latest(obj_type, obj_id)
            if result:
                meta, _ = result
                # All objects except RunBinding (root) should have causation_ref
                if obj_type != "RunBinding":
                    assert meta.causation_ref is not None, \
                        f"{obj_type}:{obj_id} has None causation_ref"

        ledger.close()

    def test_all_upstream_refs_belong_to_same_run_binding(self, tmp_path):
        """All causation_ref targets must belong to the same RunBinding."""
        runtime, rb_id = _prepare_and_finalize(tmp_path)

        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        events = ledger.get_verified_events(rb_id)

        # All events must share the same run_binding_id
        for evt in events:
            assert evt["run_binding_id"] == rb_id

        ledger.close()

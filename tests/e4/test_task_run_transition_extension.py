"""E4 tests — TaskRun.transition() extension."""

import pytest
from furina_code.contracts import TaskRun, Phase, Disposition
from furina_code.ledger import Ledger


def _make_task_run(ledger, rb="rb-1", t="t-1", tr="tr-1"):
    obj = TaskRun.create(
        run_binding_id=rb, task_id=t, task_run_id=tr,
        project_ref="p", correlation_id="c", task_revision=1,
    )
    ledger.write_object(obj.meta, {
        "task_revision": obj.task_revision, "phase": obj.phase.value,
        "disposition": obj.disposition.value, "current_refs": [],
        "open_requests": [], "started_at": obj.started_at.isoformat(),
        "terminal_reason": obj.terminal_reason,
    }, caller_organ="I2-D", expected_revision=0)
    return obj


class TestTransitionExtension:
    def test_preserves_fields_by_default(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        tr2 = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        assert tr2.current_refs == ()
        assert tr2.open_requests == ()
        assert tr2.terminal_reason is None
        ledger.close()

    def test_updates_current_refs(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        tr2 = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE,
                            current_refs=("ref-1", "ref-2"))
        assert tr2.current_refs == ("ref-1", "ref-2")
        ledger.close()

    def test_updates_open_requests(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        tr2 = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE,
                            open_requests=("req-1",))
        assert tr2.open_requests == ("req-1",)
        ledger.close()

    def test_updates_terminal_reason(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        for phase, disp in [
            (Phase.OBSERVE, Disposition.ACTIVE),
            (Phase.DELIBERATE, Disposition.ACTIVE),
            (Phase.AUTHORIZE, Disposition.ACTIVE),
            (Phase.ACT, Disposition.ACTIVE),
            (Phase.RECONCILE, Disposition.ACTIVE),
            (Phase.VERIFY, Disposition.ACTIVE),
            (Phase.ADJUDICATE, Disposition.ACTIVE),
        ]:
            tr = tr.transition("I2-D", phase, disp)
        tr2 = tr.transition("I2-D", Phase.TERMINAL, Disposition.TERMINAL,
                            terminal_reason="completed")
        assert tr2.terminal_reason == "completed"
        ledger.close()

    def test_none_preserves_existing(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        tr2 = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE,
                            current_refs=("ref-1",))
        tr3 = tr2.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE,
                             current_refs=None)
        assert tr3.current_refs == ("ref-1",)  # preserved
        ledger.close()

    def test_empty_tuple_clears(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        tr2 = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE,
                            current_refs=("ref-1",))
        tr3 = tr2.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE,
                             current_refs=())
        assert tr3.current_refs == ()
        ledger.close()

    def test_all_three_at_once(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        tr2 = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE,
                            current_refs=("r1",), open_requests=("req1",))
        assert tr2.current_refs == ("r1",)
        assert tr2.open_requests == ("req1",)
        ledger.close()

    def test_identity_still_inherited(self, tmp_path):
        """Binding identity fields still inherited from self.meta."""
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger, rb="rb-X", t="t-X", tr="tr-X")
        tr2 = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE,
                            current_refs=("r1",))
        assert tr2.meta.run_binding_id == "rb-X"
        assert tr2.meta.task_id == "t-X"
        assert tr2.meta.task_run_id == "tr-X"
        ledger.close()

    def test_persisted_to_ledger(self, tmp_path):
        """Extended fields are persisted to ledger correctly."""
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        tr2 = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE,
                            current_refs=("snap-ref", "ctx-ref"))
        ledger.write_object(tr2.meta, {
            "task_revision": tr2.task_revision, "phase": tr2.phase.value,
            "disposition": tr2.disposition.value,
            "current_refs": list(tr2.current_refs),
            "open_requests": list(tr2.open_requests),
            "started_at": tr2.started_at.isoformat(),
            "terminal_reason": tr2.terminal_reason,
        }, caller_organ="I2-D", expected_revision=1)

        result = ledger.get_latest("TaskRun", "tr-1")
        assert result is not None
        _, payload = result
        assert payload["current_refs"] == ["snap-ref", "ctx-ref"]
        ledger.close()

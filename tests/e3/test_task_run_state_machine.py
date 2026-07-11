"""E3 tests — TaskRun state machine."""

import pytest
from furina_code.contracts import (
    TaskRun, Phase, Disposition, StateTransitionInvalid, AuthorityViolation,
)
from furina_code.ledger import Ledger


def _make_task_run(ledger, run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1"):
    obj = TaskRun.create(
        run_binding_id=run_binding_id,
        task_id=task_id,
        task_run_id=task_run_id,
        project_ref="p",
        correlation_id="c",
        task_revision=1,
    )
    ledger.write_object(obj.meta, {
        "task_revision": obj.task_revision,
        "phase": obj.phase.value,
        "disposition": obj.disposition.value,
        "current_refs": [], "open_requests": [],
        "started_at": obj.started_at.isoformat(),
        "terminal_reason": obj.terminal_reason,
    }, caller_organ="I2-D", expected_revision=0)
    return obj


class TestValidTransitions:
    def test_intake_to_observe(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        new_tr = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        assert new_tr.phase == Phase.OBSERVE
        assert new_tr.disposition == Disposition.ACTIVE
        assert new_tr.meta.revision == 2
        ledger.close()

    def test_observe_to_deliberate(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        tr = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        tr = tr.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE)
        assert tr.phase == Phase.DELIBERATE
        ledger.close()

    def test_full_valid_path_to_terminal(self, tmp_path):
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
            (Phase.TERMINAL, Disposition.TERMINAL),
        ]:
            tr = tr.transition("I2-D", phase, disp)
        assert tr.phase == Phase.TERMINAL
        assert tr.meta.revision == 9
        ledger.close()


class TestP4BackEdges:
    def test_deliberate_to_observe(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        tr = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        tr = tr.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE)
        tr = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        assert tr.phase == Phase.OBSERVE
        assert tr.meta.revision == 4
        ledger.close()

    def test_deliberate_to_verify(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        tr = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        tr = tr.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE)
        tr = tr.transition("I2-D", Phase.VERIFY, Disposition.ACTIVE)
        assert tr.phase == Phase.VERIFY
        ledger.close()

    def test_authorize_to_deliberate(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        tr = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        tr = tr.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE)
        tr = tr.transition("I2-D", Phase.AUTHORIZE, Disposition.ACTIVE)
        tr = tr.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE)
        assert tr.phase == Phase.DELIBERATE
        ledger.close()

    def test_reconcile_to_deliberate(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        for phase, disp in [
            (Phase.OBSERVE, Disposition.ACTIVE),
            (Phase.DELIBERATE, Disposition.ACTIVE),
            (Phase.AUTHORIZE, Disposition.ACTIVE),
            (Phase.ACT, Disposition.ACTIVE),
            (Phase.RECONCILE, Disposition.ACTIVE),
        ]:
            tr = tr.transition("I2-D", phase, disp)
        tr = tr.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE)
        assert tr.phase == Phase.DELIBERATE
        ledger.close()

    def test_verify_to_deliberate(self, tmp_path):
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
        ]:
            tr = tr.transition("I2-D", phase, disp)
        tr = tr.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE)
        assert tr.phase == Phase.DELIBERATE
        ledger.close()

    def test_adjudicate_to_deliberate(self, tmp_path):
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
        tr = tr.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE)
        assert tr.phase == Phase.DELIBERATE
        ledger.close()


class TestRecoveryReviewRejection:
    def test_recovery_review_to_active_rejected(self, tmp_path):
        """E3 has no RecoveryVerdict; recovery_review→active must be rejected."""
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        # recovery_review is not reachable from intake/active in the transition table,
        # so we cannot even enter recovery_review via transition(). This tests that
        # the state machine has no recovery_review edges at all.
        with pytest.raises(StateTransitionInvalid):
            tr.transition("I2-D", Phase.INTAKE, Disposition.RECOVERY_REVIEW)
        ledger.close()


class TestInvalidTransitions:
    def test_intake_to_act_rejected(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        with pytest.raises(StateTransitionInvalid):
            tr.transition("I2-D", Phase.ACT, Disposition.ACTIVE)
        ledger.close()

    def test_act_to_verify_rejected(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        for phase, disp in [
            (Phase.OBSERVE, Disposition.ACTIVE),
            (Phase.DELIBERATE, Disposition.ACTIVE),
            (Phase.AUTHORIZE, Disposition.ACTIVE),
            (Phase.ACT, Disposition.ACTIVE),
        ]:
            tr = tr.transition("I2-D", phase, disp)
        with pytest.raises(StateTransitionInvalid):
            tr.transition("I2-D", Phase.VERIFY, Disposition.ACTIVE)
        ledger.close()

    def test_verify_to_terminal_rejected(self, tmp_path):
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
        ]:
            tr = tr.transition("I2-D", phase, disp)
        with pytest.raises(StateTransitionInvalid):
            tr.transition("I2-D", Phase.TERMINAL, Disposition.TERMINAL)
        ledger.close()

    def test_paused_cannot_advance_phase(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        tr = tr.transition("I2-D", Phase.INTAKE, Disposition.PAUSED)
        with pytest.raises(StateTransitionInvalid):
            tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        ledger.close()

    def test_manual_intervention_cannot_auto_return(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        tr = tr.transition("I2-D", Phase.INTAKE, Disposition.MANUAL_INTERVENTION)
        with pytest.raises(StateTransitionInvalid):
            tr.transition("I2-D", Phase.INTAKE, Disposition.ACTIVE)
        ledger.close()

    def test_unknown_state_value_rejected(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        with pytest.raises((StateTransitionInvalid, AttributeError, ValueError)):
            tr.transition("I2-D", "bogus_phase", Disposition.ACTIVE)
        ledger.close()

    def test_observe_to_authorize_rejected(self, tmp_path):
        """observe cannot skip deliberate."""
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        tr = tr.transition("I2-D", Phase.OBSERVE, Disposition.ACTIVE)
        with pytest.raises(StateTransitionInvalid):
            tr.transition("I2-D", Phase.AUTHORIZE, Disposition.ACTIVE)
        ledger.close()

    def test_reconcile_to_act_rejected(self, tmp_path):
        """reconcile cannot go backwards to act."""
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        for phase, disp in [
            (Phase.OBSERVE, Disposition.ACTIVE),
            (Phase.DELIBERATE, Disposition.ACTIVE),
            (Phase.AUTHORIZE, Disposition.ACTIVE),
            (Phase.ACT, Disposition.ACTIVE),
            (Phase.RECONCILE, Disposition.ACTIVE),
        ]:
            tr = tr.transition("I2-D", phase, disp)
        with pytest.raises(StateTransitionInvalid):
            tr.transition("I2-D", Phase.ACT, Disposition.ACTIVE)
        ledger.close()

    def test_act_to_deliberate_rejected(self, tmp_path):
        """act cannot go back to deliberate (must go through reconcile)."""
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        tr = _make_task_run(ledger)
        for phase, disp in [
            (Phase.OBSERVE, Disposition.ACTIVE),
            (Phase.DELIBERATE, Disposition.ACTIVE),
            (Phase.AUTHORIZE, Disposition.ACTIVE),
            (Phase.ACT, Disposition.ACTIVE),
        ]:
            tr = tr.transition("I2-D", phase, disp)
        with pytest.raises(StateTransitionInvalid):
            tr.transition("I2-D", Phase.DELIBERATE, Disposition.ACTIVE)
        ledger.close()

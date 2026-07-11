"""E3 tests — restart continuity rebuild."""

from furina_code.contracts import RunBinding, TaskDossier, TaskRun, Checkpoint, Phase, Disposition
from furina_code.ledger import Ledger
from furina_code.continuity import rebuild_continuity


class TestRestartContinuity:
    def test_rebuild_after_restart(self, tmp_path):
        db_path = str(tmp_path / "test.sqlite3")

        # Phase 1: Create data
        ledger = Ledger(db_path)
        ledger.open()

        # Create RunBinding
        rb = RunBinding.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="proj-1", correlation_id="corr-1",
            subject_ref="user-1", user_ref="user-1", task_ref="task-1",
            allowed_tool_classes=("file_write",), source_refs=("s1",),
        )
        ledger.write_object(rb.meta, {
            "subject_ref": rb.subject_ref, "user_ref": rb.user_ref,
            "project_ref": rb.project_ref, "task_ref": rb.task_ref,
            "allowed_tool_classes": list(rb.allowed_tool_classes),
            "status": rb.status.value, "source_refs": list(rb.source_refs),
        }, caller_organ="I1-A", expected_revision=0)

        # Create TaskDossier
        td = TaskDossier.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="proj-1", correlation_id="corr-1",
            source_intent_ref="si-1", structured_goal="create welcome.txt",
            success_criteria=("file exists",), scope=("notes/",),
            exclusions=(), unknowns=(), risk_class="low",
            user_constraints=(),
        )
        ledger.write_object(td.meta, {
            "source_intent_ref": td.source_intent_ref,
            "structured_goal": td.structured_goal,
            "success_criteria": list(td.success_criteria),
            "scope": list(td.scope), "exclusions": list(td.exclusions),
            "unknowns": list(td.unknowns), "risk_class": td.risk_class,
            "user_constraints": list(td.user_constraints),
            "status": td.status.value,
        }, caller_organ="I2-A", expected_revision=0)

        # Create TaskRun
        tr = TaskRun.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="proj-1", correlation_id="corr-1",
            task_revision=1,
        )
        ledger.write_object(tr.meta, {
            "task_revision": tr.task_revision, "phase": tr.phase.value,
            "disposition": tr.disposition.value, "current_refs": [],
            "open_requests": [], "started_at": tr.started_at.isoformat(),
            "terminal_reason": tr.terminal_reason,
        }, caller_organ="I2-D", expected_revision=0)

        # Transition TaskRun: intake/active -> observe/active
        tr2 = tr.transition("I2-D", "rb-1", "t-1", "tr-1", "proj-1", "corr-1",
                           Phase.OBSERVE, Disposition.ACTIVE)
        ledger.write_object(tr2.meta, {
            "task_revision": tr2.task_revision, "phase": tr2.phase.value,
            "disposition": tr2.disposition.value, "current_refs": [],
            "open_requests": [], "started_at": tr2.started_at.isoformat(),
            "terminal_reason": tr2.terminal_reason,
        }, caller_organ="I2-D", expected_revision=1)

        # Create Checkpoint
        cp = Checkpoint.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="proj-1", correlation_id="corr-1",
            task_revision=1, phase=Phase.OBSERVE,
            disposition=Disposition.ACTIVE,
            event_cursor=4, pending_requests=(), snapshot_ref=None,
            reason="test checkpoint",
        )
        ledger.write_object(cp.meta, {
            "task_revision": cp.task_revision, "phase": cp.phase.value,
            "disposition": cp.disposition.value, "event_cursor": cp.event_cursor,
            "pending_requests": list(cp.pending_requests),
            "pending_actions": list(cp.pending_actions),
            "snapshot_ref": cp.snapshot_ref, "ticket_refs": list(cp.ticket_refs),
            "reason": cp.reason,
        }, caller_organ="I1-C", expected_revision=0)

        # Close
        ledger.close()

        # Phase 2: Reopen and rebuild
        ledger2 = Ledger(db_path)
        ledger2.open()

        view = rebuild_continuity(ledger2, "rb-1")
        assert view.run_binding_id == "rb-1"
        assert view.last_event_sequence == 5  # 5 events total
        assert view.task_phase == "observe"
        assert view.task_disposition == "active"
        assert view.open_request_refs == ()
        assert view.unresolved_action_refs == ()

        ledger2.close()

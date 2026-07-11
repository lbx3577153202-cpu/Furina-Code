"""E4 tests — CompletionVerdict creation."""

from furina_code.contracts import VerificationVerdict
from furina_code.readonly.completion import create_completion_verdict


class TestCompletionVerdict:
    def test_all_pass(self):
        vvs = [
            VerificationVerdict.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                plan_ref="sha256:vp", outcome="pass",
                checked_conditions=("cond_a",), envelope_id=f"vv-{i}",
            )
            for i in range(3)
        ]
        cv = create_completion_verdict(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_run_ref="sha256:tr", candidate_ref="sha256:ce",
            verdicts=vvs,
        )
        assert cv.outcome == "completed"
        assert len(cv.completed_items) == 3
        assert len(cv.incomplete_items) == 0

    def test_one_fails(self):
        vvs = [
            VerificationVerdict.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                plan_ref="sha256:vp", outcome="pass",
                checked_conditions=("cond_a",), envelope_id="vv-0",
            ),
            VerificationVerdict.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                plan_ref="sha256:vp", outcome="fail",
                checked_conditions=("cond_b",),
                failed_conditions=("cond_b",), envelope_id="vv-1",
            ),
        ]
        cv = create_completion_verdict(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_run_ref="sha256:tr", candidate_ref="sha256:ce",
            verdicts=vvs,
        )
        assert cv.outcome == "failed"
        assert "cond_a" in cv.completed_items
        assert "cond_b" in cv.incomplete_items

    def test_user_effect_present(self):
        vvs = [
            VerificationVerdict.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                plan_ref="sha256:vp", outcome="pass",
                checked_conditions=("cond_a",),
            ),
        ]
        cv = create_completion_verdict(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_run_ref="sha256:tr", candidate_ref="sha256:ce",
            verdicts=vvs,
        )
        assert "No project files modified" in cv.user_effect
        assert "RecoveryVerdict not implemented" in cv.user_effect

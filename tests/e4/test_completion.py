"""E4 tests — CompletionVerdict creation."""

from furina_code.contracts import VerificationVerdict
from furina_code.readonly.completion import create_completion_verdict


class TestCompletionVerdict:
    def test_all_pass(self):
        vvs = [
            VerificationVerdict.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                plan_ref="sha256:vp", evidence_refs=("sha256:ev",),
                criterion_results={"cond_a": "pass"}, coverage=1.0,
                outcome="pass", envelope_id=f"vv-{i}",
            )
            for i in range(3)
        ]
        agg_ref = vvs[0].meta.integrity_ref
        cv = create_completion_verdict(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_revision=1, task_run_ref="sha256:tr",
            verification_ref=agg_ref,
            candidate_ref="sha256:ce",
            outcome="completed",
            completed_items=("cond_a", "cond_b", "cond_c"),
        )
        assert cv.outcome == "completed"
        assert cv.no_project_side_effect is True

    def test_one_fails(self):
        cv = create_completion_verdict(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_revision=1, task_run_ref="sha256:tr",
            verification_ref="sha256:vv",
            candidate_ref="sha256:ce",
            outcome="not_completed",
            completed_items=("cond_a",),
            incomplete_items=("cond_b",),
        )
        assert cv.outcome == "not_completed"

    def test_user_effect_present(self):
        cv = create_completion_verdict(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_revision=1, task_run_ref="sha256:tr",
            verification_ref="sha256:vv",
            candidate_ref="sha256:ce",
            outcome="completed",
            user_effect="No project files modified. RecoveryVerdict not implemented.",
        )
        assert "No project files modified" in cv.user_effect

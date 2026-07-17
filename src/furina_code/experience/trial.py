"""E7's conservative second-task experience loop."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from ..contracts import (
    BoundActionPlan,
    CompletionVerdict,
    ContractInvalid,
    ExperienceCandidate,
    ExperienceLifecycleVerdict,
    ExperienceMatch,
    TrialUseRecord,
)

if TYPE_CHECKING:
    from ..ledger import Ledger


def _payload(obj: Any) -> dict[str, Any]:
    if isinstance(obj, ExperienceCandidate):
        return {
            "source_completion_refs": list(obj.source_completion_refs),
            "success_and_failure_facts": list(obj.success_and_failure_facts),
            "lesson": obj.lesson, "applicability": list(obj.applicability),
            "contraindications": list(obj.contraindications), "risk": obj.risk,
            "confidence": obj.confidence, "status": obj.status,
        }
    if isinstance(obj, ExperienceMatch):
        return {
            "task_revision": obj.task_revision, "candidate_refs": list(obj.candidate_refs),
            "match_reasons": list(obj.match_reasons), "mismatch_reasons": list(obj.mismatch_reasons),
            "risk_warnings": list(obj.risk_warnings), "recommendation": obj.recommendation,
        }
    if isinstance(obj, TrialUseRecord):
        return {
            "experience_ref": obj.experience_ref, "task_revision": obj.task_revision,
            "usage_mode": obj.usage_mode, "influence_ref": obj.influence_ref,
            "completion_ref": obj.completion_ref, "result": obj.result,
        }
    if isinstance(obj, BoundActionPlan):
        return {
            "candidate_ref": obj.candidate_ref, "task_revision": obj.task_revision,
            "baseline_snapshot_ref": obj.baseline_snapshot_ref,
            "baseline_snapshot_sha256": obj.baseline_snapshot_sha256,
            "target_scope": list(obj.target_scope), "operations": list(obj.operations),
            "expected_diff": obj.expected_diff, "risk": obj.risk,
            "rollback_or_compensation": obj.rollback_or_compensation,
            "preconditions": list(obj.preconditions),
            "experience_match_ref": obj.experience_match_ref,
        }
    if isinstance(obj, ExperienceLifecycleVerdict):
        return {
            "experience_ref": obj.experience_ref, "evidence_refs": list(obj.evidence_refs),
            "previous_status": obj.previous_status, "new_status": obj.new_status,
            "reason": obj.reason, "user_revision_ref": obj.user_revision_ref,
        }
    raise ContractInvalid(f"Unsupported experience object: {type(obj).__name__}")


def write_experience_object(ledger: Ledger, obj: Any, expected_revision: int) -> None:
    ledger.write_object(obj.meta, _payload(obj), obj.meta.owner_organ, expected_revision)


def extract_completed_write_experience(completion: CompletionVerdict) -> ExperienceCandidate:
    """A completion can create a candidate; it cannot promote itself."""
    if completion.outcome != "completed" or completion.no_project_side_effect:
        raise ContractInvalid("Only a completed controlled-write task may produce this E7 experience")
    return ExperienceCandidate.create(
        run_binding_id=completion.meta.run_binding_id, task_id=completion.meta.task_id,
        task_run_id=completion.meta.task_run_id, project_ref=completion.meta.project_ref,
        correlation_id=completion.meta.correlation_id,
        source_completion_refs=(completion.meta.integrity_ref,),
        success_and_failure_facts=(
            "single-file create was reconciled and verified",
            "ticket was single-use and consumed before the write",
        ),
        lesson="For a low-risk notes file, bind a fresh clean snapshot and verify exact content after writing.",
        applicability=("low-risk", "single-file-create", "notes/"),
        contraindications=("overwrite", "delete", "unknown outcome", "scope drift"),
        risk="low", confidence="one completed task only", status="candidate",
        causation_ref=completion.meta.integrity_ref,
    )


def match_experience_for_second_task(
    experience: ExperienceCandidate,
    *,
    run_binding_id: str,
    task_id: str,
    task_run_id: str,
    project_ref: str,
    correlation_id: str,
    task_revision: int,
    target_scope: tuple[str, ...],
    risk: str,
) -> ExperienceMatch:
    """Return conditional guidance only; never an authorization or action plan."""
    same_task = experience.meta.task_id == task_id
    scope_match = "notes/" in target_scope and "notes/" in experience.applicability
    risk_match = risk == experience.risk
    reasons = tuple(reason for ok, reason in (
        (scope_match, "same allowed notes scope"),
        (risk_match, "same low-risk class"),
        (not same_task, "independent second task"),
    ) if ok)
    mismatches = tuple(reason for ok, reason in (
        (scope_match, "scope differs from experience applicability"),
        (risk_match, "risk differs from experience applicability"),
        (not same_task, "experience cannot validate itself on the source task"),
    ) if not ok)
    usable = scope_match and risk_match and not same_task and experience.status in {"candidate", "trial_eligible", "conditional"}
    return ExperienceMatch.create(
        run_binding_id=run_binding_id, task_id=task_id, task_run_id=task_run_id,
        project_ref=project_ref, correlation_id=correlation_id, task_revision=task_revision,
        candidate_refs=(experience.meta.integrity_ref,) if usable else (),
        match_reasons=reasons, mismatch_reasons=mismatches,
        risk_warnings=("experience is guidance only; repeat observation, authorization and verification",),
        recommendation=(
            "candidate_guidance_only: reuse the low-risk shape, then re-run G2–G7"
            if usable else "do_not_apply_experience"
        ),
        causation_ref=experience.meta.integrity_ref,
    )


def record_trial_use(
    experience: ExperienceCandidate,
    match: ExperienceMatch,
    plan: BoundActionPlan,
    completion: CompletionVerdict,
) -> TrialUseRecord:
    """Record a trial use with full causal chain validation.

    The chain must be: experience -> match -> plan -> completion.
    """
    # 1. Experience must be in match.candidate_refs
    if not match.candidate_refs or experience.meta.integrity_ref not in match.candidate_refs:
        raise ContractInvalid("Trial use requires a matching conditional recommendation")
    # 2. Must be a second task, not the source task
    if completion.meta.task_id == experience.meta.task_id:
        raise ContractInvalid("Trial use must be a second task, not the source task")
    # 3. Plan must carry the experience_match_ref
    if not plan.experience_match_ref:
        raise ContractInvalid("Plan must carry an experience_match_ref to enable trial use")
    # 4. Plan's experience_match_ref must match the match's integrity ref
    if plan.experience_match_ref != match.meta.integrity_ref:
        raise ContractInvalid("Plan's experience_match_ref must match the match's integrity ref")
    # 5. Completion must reference the plan
    if completion.action_plan_ref != plan.meta.integrity_ref:
        raise ContractInvalid("Completion must reference the executed action plan")
    # 6. Causal chain: match, completion, and plan must share the same task identity
    if match.meta.task_id != completion.meta.task_id:
        raise ContractInvalid("Match and completion must belong to the same second-round task")
    if match.meta.task_run_id != completion.meta.task_run_id:
        raise ContractInvalid("Match and completion must belong to the same second-round task run")
    if match.meta.project_ref != completion.meta.project_ref:
        raise ContractInvalid("Match and completion must belong to the same project")
    if match.meta.correlation_id != completion.meta.correlation_id:
        raise ContractInvalid("Match and completion must share the same correlation")
    if match.task_revision != completion.task_revision:
        raise ContractInvalid("Match and completion must reference the same task revision")
    # 7. Plan must belong to the same task
    if plan.meta.task_id != completion.meta.task_id:
        raise ContractInvalid("Plan must belong to the same task as completion")
    result = "completed" if completion.outcome == "completed" else "not_completed"
    return TrialUseRecord.create(
        run_binding_id=completion.meta.run_binding_id, task_id=completion.meta.task_id,
        task_run_id=completion.meta.task_run_id, project_ref=completion.meta.project_ref,
        correlation_id=completion.meta.correlation_id, experience_ref=experience.meta.integrity_ref,
        task_revision=completion.task_revision, influence_ref=match.meta.integrity_ref,
        completion_ref=completion.meta.integrity_ref, result=result,
        causation_ref=match.meta.integrity_ref,
    )


def adjudicate_trial(
    experience: ExperienceCandidate,
    trial: TrialUseRecord,
) -> ExperienceLifecycleVerdict:
    """One independent trial makes an experience conditional, never reusable."""
    successful = trial.result == "completed"
    new_status = "conditional" if successful else "degraded"
    return ExperienceLifecycleVerdict.create(
        run_binding_id=trial.meta.run_binding_id, task_id=trial.meta.task_id,
        task_run_id=trial.meta.task_run_id, project_ref=trial.meta.project_ref,
        correlation_id=trial.meta.correlation_id, experience_ref=experience.meta.integrity_ref,
        evidence_refs=(trial.meta.integrity_ref, trial.completion_ref),
        previous_status=experience.status, new_status=new_status,
        reason=("independent second task completed; retain only conditional guidance"
                if successful else "second task did not complete; degrade the experience"),
        causation_ref=trial.meta.integrity_ref,
    )

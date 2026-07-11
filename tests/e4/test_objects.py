"""E4 tests — new formal objects."""

import pytest
from furina_code.contracts import (
    BackendProfile, ContextEnvelope, CandidateEnvelope, ProjectSnapshot,
    EvidenceEnvelope, VerificationPlan, VerificationVerdict, CompletionVerdict,
    AuthorityViolation, ContractInvalid, OWNER_MAP,
)
from furina_code.ledger import Ledger
from furina_code.contracts.meta import now_utc


class TestNewOWNERMap:
    def test_all_e4_types_registered(self):
        for t in ["BackendProfile", "ContextEnvelope", "CandidateEnvelope",
                   "ProjectSnapshot", "EvidenceEnvelope", "VerificationPlan",
                   "VerificationVerdict", "CompletionVerdict"]:
            assert t in OWNER_MAP

    def test_e4_owners_correct(self):
        assert OWNER_MAP["BackendProfile"] == "I2-B"
        assert OWNER_MAP["ContextEnvelope"] == "I2-C"
        assert OWNER_MAP["CandidateEnvelope"] == "I2-D"
        assert OWNER_MAP["ProjectSnapshot"] == "I3-A"
        assert OWNER_MAP["EvidenceEnvelope"] == "I4-C"
        assert OWNER_MAP["VerificationPlan"] == "I4-D"
        assert OWNER_MAP["VerificationVerdict"] == "I4-D"
        assert OWNER_MAP["CompletionVerdict"] == "I4-E"


class TestBackendProfile:
    def test_create(self):
        bp = BackendProfile.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            provider_ref="test-provider",
            capabilities=("git_read",),
        )
        assert bp.meta.object_type == "BackendProfile"
        assert bp.meta.owner_organ == "I2-B"
        assert bp.provider_ref == "test-provider"
        assert bp.health == "available"
        assert bp.meta.integrity_ref.startswith("sha256:")

    def test_owner_mismatch(self, tmp_path):
        bp = BackendProfile.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            provider_ref="test", capabilities=(),
        )
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        with pytest.raises(AuthorityViolation):
            ledger.write_object(bp.meta, {
                "provider_ref": bp.provider_ref, "capabilities": [],
                "limits": {}, "health": bp.health,
                "credential_mode": bp.credential_mode,
                "data_policy_ref": bp.data_policy_ref,
                "last_checked_at": bp.last_checked_at.isoformat(),
                "backend_id": bp.backend_id, "backend_kind": bp.backend_kind,
            }, caller_organ="I9-X", expected_revision=0)
        ledger.close()

    def test_write_to_ledger(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        bp = BackendProfile.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            provider_ref="test", capabilities=("git_read",),
            backend_id="test-backend",
        )
        ledger.write_object(bp.meta, {
            "provider_ref": bp.provider_ref, "capabilities": list(bp.capabilities),
            "limits": bp.limits, "health": bp.health,
            "credential_mode": bp.credential_mode,
            "data_policy_ref": bp.data_policy_ref,
            "last_checked_at": bp.last_checked_at.isoformat(),
            "backend_id": bp.backend_id, "backend_kind": bp.backend_kind,
        }, caller_organ="I2-B", expected_revision=0)
        assert ledger.get_head_revision("BackendProfile", "test-backend") == 1
        ledger.close()


class TestContextEnvelope:
    def test_create(self):
        ce = ContextEnvelope.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_revision=1, purpose="test",
            snapshot_ref="sha256:aa", task_dossier_ref="sha256:bb",
            included_refs=("sha256:aa",), redactions=("paths",),
            classification_summary="project_internal",
            disclosure_basis="allowlist",
            backend_ref="sha256:cc",
            context_digest="sha256:dd",
        )
        assert ce.meta.object_type == "ContextEnvelope"
        assert ce.purpose == "test"
        assert ce.context_digest == "sha256:dd"


class TestCandidateEnvelope:
    def test_create(self):
        ce = CandidateEnvelope.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            candidate_type="repository_baseline_report",
            backend_profile_ref="sha256:aa",
            backend_session_ref="session-1",
            context_ref="sha256:bb",
            content_ref="sha256:cc",
            candidate_digest="abc123",
        )
        assert ce.meta.object_type == "CandidateEnvelope"
        assert ce.candidate_digest == "abc123"
        assert ce.status == "accepted"


class TestProjectSnapshot:
    def test_create(self):
        ps = ProjectSnapshot.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            head_sha="a" * 40, branch="main",
            status_lines=(), tracked_count=10, untracked_count=0,
            is_clean=True, pyproject_exists=True,
            pyproject_sha256="sha256:abc",
            requires_python=">=3.12",
            runtime_deps=(), dev_deps=("pytest",),
            pytest_testpaths=("tests",),
            ci_config_exists=True, ci_config_sha256="sha256:def",
            blind_spots=(), snapshot_sha256="sha256:123",
        )
        assert ps.meta.object_type == "ProjectSnapshot"
        assert ps.observation_scope == "read-only repository baseline"
        assert ps.freshness_policy == "point-in-time"


class TestEvidenceEnvelope:
    def test_create(self):
        ev = EvidenceEnvelope.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            claim_scope="verification:test",
            evidence_type="existence_check", source_ref="test",
            claim="HEAD matches",
        )
        assert ev.meta.object_type == "EvidenceEnvelope"
        assert ev.claim_scope == "verification:test"


class TestVerificationPlan:
    def test_create(self):
        vp = VerificationPlan.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_revision=1,
            candidate_ref="sha256:aa",
            success_criteria_map={"HEAD observed": "snapshot_head_match"},
            success_criteria=("HEAD observed",),
            checks=("snapshot_head_match",),
        )
        assert vp.meta.object_type == "VerificationPlan"
        assert vp.task_revision == 1


class TestVerificationVerdict:
    def test_create_pass(self):
        vv = VerificationVerdict.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            plan_ref="sha256:aa", evidence_refs=("sha256:ev",),
            criterion_results={"HEAD observed": "pass"},
            coverage=1.0, outcome="pass", reason="all passed",
        )
        assert vv.outcome == "pass"
        assert vv.coverage == 1.0

    def test_create_fail(self):
        vv = VerificationVerdict.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            plan_ref="sha256:aa", evidence_refs=("sha256:ev",),
            criterion_results={"HEAD observed": "fail"},
            coverage=0.0, failed_checks=("snapshot_head_match",),
            outcome="fail", reason="HEAD mismatch",
        )
        assert vv.outcome == "fail"

    def test_invalid_outcome_rejected(self):
        with pytest.raises(ContractInvalid):
            VerificationVerdict.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                plan_ref="sha256:aa", evidence_refs=(),
                criterion_results={}, coverage=0.0,
                outcome="INVALID_OUTCOME",
            )


class TestCompletionVerdict:
    def test_create_completed(self):
        cv = CompletionVerdict.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_revision=1, task_run_ref="sha256:aa",
            verification_ref="sha256:vv",
            candidate_ref="sha256:bb",
            outcome="completed",
            completed_items=("HEAD", "branch"),
        )
        assert cv.outcome == "completed"
        assert cv.no_project_side_effect is True

    def test_create_failed(self):
        cv = CompletionVerdict.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_revision=1, task_run_ref="sha256:aa",
            verification_ref="sha256:vv",
            candidate_ref="sha256:bb",
            outcome="not_completed",
            incomplete_items=("HEAD",),
        )
        assert cv.outcome == "not_completed"

    def test_invalid_outcome_rejected(self):
        with pytest.raises(ContractInvalid):
            CompletionVerdict.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                task_revision=1, task_run_ref="sha256:aa",
                verification_ref="sha256:vv",
                candidate_ref="sha256:bb",
                outcome="INVALID",
            )


class TestE4ObjectsOwnerEnforcement:
    @pytest.mark.parametrize("obj_type,owner", [
        ("BackendProfile", "I2-B"),
        ("ContextEnvelope", "I2-C"),
        ("CandidateEnvelope", "I2-D"),
        ("ProjectSnapshot", "I3-A"),
        ("EvidenceEnvelope", "I4-C"),
        ("VerificationPlan", "I4-D"),
        ("VerificationVerdict", "I4-D"),
        ("CompletionVerdict", "I4-E"),
    ])
    def test_owner_enforced_on_write(self, tmp_path, obj_type, owner):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()

        creators = {
            "BackendProfile": lambda: BackendProfile.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                provider_ref="test", capabilities=(), backend_id="b1",
            ),
            "ContextEnvelope": lambda: ContextEnvelope.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                task_revision=1, purpose="test",
                snapshot_ref="s", task_dossier_ref="d",
                included_refs=(), redactions=(),
                classification_summary="test", disclosure_basis="test",
                backend_ref="b", context_digest="sha256:0",
                envelope_id="ctx-1",
            ),
            "CandidateEnvelope": lambda: CandidateEnvelope.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                candidate_type="repository_baseline_report",
                backend_profile_ref="b", backend_session_ref="s",
                context_ref="c", content_ref="cr",
                candidate_digest="abc",
            ),
            "ProjectSnapshot": lambda: ProjectSnapshot.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                head_sha="a" * 40, branch="main", status_lines=(),
                tracked_count=0, untracked_count=0, is_clean=True,
                pyproject_exists=False, pyproject_sha256=None,
                requires_python=None, runtime_deps=(), dev_deps=(),
                pytest_testpaths=(), ci_config_exists=False,
                ci_config_sha256=None, blind_spots=(),
                snapshot_sha256="sha256:0",
            ),
            "EvidenceEnvelope": lambda: EvidenceEnvelope.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                claim_scope="test", evidence_type="test",
                source_ref="test", claim="test", envelope_id="ev-1",
            ),
            "VerificationPlan": lambda: VerificationPlan.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                task_revision=1, candidate_ref="sha256:0",
                success_criteria_map={}, success_criteria=(), checks=(),
                envelope_id="vp-1",
            ),
            "VerificationVerdict": lambda: VerificationVerdict.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                plan_ref="sha256:0", evidence_refs=(),
                criterion_results={}, coverage=0.0,
                outcome="not_run", envelope_id="vv-1",
            ),
            "CompletionVerdict": lambda: CompletionVerdict.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                task_revision=1, task_run_ref="sha256:0",
                verification_ref="sha256:0",
                candidate_ref="sha256:0", outcome="not_completed",
                envelope_id="cv-1",
            ),
        }

        obj = creators[obj_type]()
        with pytest.raises(AuthorityViolation):
            ledger.write_object(obj.meta, {}, caller_organ="I9-X", expected_revision=0)

        ledger.close()

    def test_causation_ref_required_for_non_root(self):
        """Non-root objects should have causation_ref set."""
        ce = ContextEnvelope.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_revision=1, purpose="test",
            snapshot_ref="s", task_dossier_ref="d",
            included_refs=(), redactions=(),
            classification_summary="test", disclosure_basis="test",
            backend_ref="b", context_digest="sha256:0",
            causation_ref="sha256:parent",
        )
        assert ce.meta.causation_ref == "sha256:parent"

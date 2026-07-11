"""E4 tests — new formal objects."""

import pytest
from furina_code.contracts import (
    BackendProfile, ContextEnvelope, CandidateEnvelope, ProjectSnapshot,
    EvidenceEnvelope, VerificationPlan, VerificationVerdict, CompletionVerdict,
    RunBinding, TaskDossier, TaskRun, Checkpoint,
    AuthorityViolation, ContractInvalid, OWNER_MAP,
    LedgerWriteFailed,
)
from furina_code.ledger import Ledger
from furina_code.contracts.meta import now_utc


class TestNewOWNERMap:
    def test_all_e4_types_registered(self):
        assert "BackendProfile" in OWNER_MAP
        assert "ContextEnvelope" in OWNER_MAP
        assert "CandidateEnvelope" in OWNER_MAP
        assert "ProjectSnapshot" in OWNER_MAP
        assert "EvidenceEnvelope" in OWNER_MAP
        assert "VerificationPlan" in OWNER_MAP
        assert "VerificationVerdict" in OWNER_MAP
        assert "CompletionVerdict" in OWNER_MAP

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
            backend_id="test-backend", backend_kind="llm",
            capabilities=("file_read",), timeout_seconds=300,
        )
        assert bp.meta.object_type == "BackendProfile"
        assert bp.meta.owner_organ == "I2-B"
        assert bp.backend_id == "test-backend"
        assert bp.status == "active"
        assert bp.meta.integrity_ref.startswith("sha256:")

    def test_owner_mismatch(self, tmp_path):
        bp = BackendProfile.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            backend_id="test-backend", backend_kind="llm",
            capabilities=(), timeout_seconds=300,
        )
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        with pytest.raises(AuthorityViolation):
            ledger.write_object(bp.meta, {
                "backend_id": bp.backend_id, "backend_kind": bp.backend_kind,
                "capabilities": [], "timeout_seconds": bp.timeout_seconds,
                "status": bp.status,
            }, caller_organ="I9-X", expected_revision=0)
        ledger.close()

    def test_write_to_ledger(self, tmp_path):
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()
        bp = BackendProfile.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            backend_id="test-backend", backend_kind="llm",
            capabilities=("file_read",), timeout_seconds=300,
        )
        ledger.write_object(bp.meta, {
            "backend_id": bp.backend_id, "backend_kind": bp.backend_kind,
            "capabilities": list(bp.capabilities),
            "timeout_seconds": bp.timeout_seconds, "status": bp.status,
        }, caller_organ="I2-B", expected_revision=0)
        assert ledger.get_head_revision("BackendProfile", "test-backend") == 1
        ledger.close()


class TestContextEnvelope:
    def test_create(self):
        ce = ContextEnvelope.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            snapshot_ref="sha256:aa", task_dossier_ref="sha256:bb",
            context_payload={"goal": "test"},
        )
        assert ce.meta.object_type == "ContextEnvelope"
        assert ce.instruction_profile_id == "e4-repository-baseline-v1"


class TestCandidateEnvelope:
    def test_create(self):
        ce = CandidateEnvelope.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            context_envelope_ref="sha256:aa",
            candidate_path="/tmp/candidate.json",
            candidate_sha256="abc123",
            backend_id="test-backend",
        )
        assert ce.meta.object_type == "CandidateEnvelope"
        assert ce.candidate_sha256 == "abc123"


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
        assert ps.head_sha == "a" * 40
        assert ps.is_clean is True


class TestEvidenceEnvelope:
    def test_create(self):
        ev = EvidenceEnvelope.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            evidence_type="existence_check", source_ref="test",
            claim="HEAD matches",
        )
        assert ev.meta.object_type == "EvidenceEnvelope"
        assert ev.integrity_status == "verified"


class TestVerificationPlan:
    def test_create(self):
        vp = VerificationPlan.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            candidate_ref="sha256:aa",
            success_criteria=("HEAD",),
            steps=("snapshot_head_match",),
        )
        assert vp.meta.object_type == "VerificationPlan"
        assert vp.steps == ("snapshot_head_match",)


class TestVerificationVerdict:
    def test_create_pass(self):
        vv = VerificationVerdict.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            plan_ref="sha256:aa", outcome="pass",
            checked_conditions=("snapshot_head_match",),
        )
        assert vv.outcome == "pass"
        assert vv.failed_conditions == ()

    def test_create_fail(self):
        vv = VerificationVerdict.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            plan_ref="sha256:aa", outcome="fail",
            checked_conditions=("snapshot_head_match",),
            failed_conditions=("snapshot_head_match",),
        )
        assert vv.outcome == "fail"


class TestCompletionVerdict:
    def test_create_completed(self):
        cv = CompletionVerdict.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_run_ref="sha256:aa", candidate_ref="sha256:bb",
            outcome="completed",
            completed_items=("HEAD", "branch"),
        )
        assert cv.outcome == "completed"

    def test_create_failed(self):
        cv = CompletionVerdict.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_run_ref="sha256:aa", candidate_ref="sha256:bb",
            outcome="failed",
            incomplete_items=("HEAD",),
        )
        assert cv.outcome == "failed"


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
        """Each E4 object type must reject writes from wrong owner."""
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()

        creators = {
            "BackendProfile": lambda: BackendProfile.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                backend_id="b1", backend_kind="llm",
                capabilities=(), timeout_seconds=300,
            ),
            "ContextEnvelope": lambda: ContextEnvelope.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                snapshot_ref="s", task_dossier_ref="d",
                context_payload={}, envelope_id="ctx-1",
            ),
            "CandidateEnvelope": lambda: CandidateEnvelope.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                context_envelope_ref="c", candidate_path="/tmp/x",
                candidate_sha256="abc", backend_id="b1",
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
                evidence_type="test", source_ref="test", claim="test",
                envelope_id="ev-1",
            ),
            "VerificationPlan": lambda: VerificationPlan.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                candidate_ref="sha256:0", success_criteria=(),
                steps=(), envelope_id="vp-1",
            ),
            "VerificationVerdict": lambda: VerificationVerdict.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                plan_ref="sha256:0", outcome="pass",
                checked_conditions=(), envelope_id="vv-1",
            ),
            "CompletionVerdict": lambda: CompletionVerdict.create(
                run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
                project_ref="p", correlation_id="c",
                task_run_ref="sha256:0", candidate_ref="sha256:0",
                outcome="completed", envelope_id="cv-1",
            ),
        }

        obj = creators[obj_type]()
        wrong_owner = "I9-X"
        with pytest.raises(AuthorityViolation):
            ledger.write_object(obj.meta, {}, caller_organ=wrong_owner, expected_revision=0)

        ledger.close()

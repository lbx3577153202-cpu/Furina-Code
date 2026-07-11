"""E4.5 tests — runtime boundary, G7 failure integration, G6 exact mapping, G7 current heads."""

import json
from pathlib import Path
from unittest.mock import patch
from furina_code.cli import main as cli_main
from furina_code.ledger import Ledger
from furina_code.readonly.verification import evaluate_gate, GateResult
from furina_code.readonly.verification import EvidenceEnvelope
from furina_code.contracts.objects import VerificationVerdict
from tests.e4.conftest import write_candidate_file, get_run_binding_id


def _prepare(tmp_path):
    repo = str(Path(__file__).resolve().parents[2])
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cli_main(["inspect", "prepare", "--workspace", repo, "--runtime-dir", str(runtime)])
    return runtime


# === Section 1: Runtime boundary ===

class TestRuntimeBoundary:
    def test_subdirectory_workspace_rejects_runtime_inside_repo(self, tmp_path):
        """workspace=repo/tests/e4, runtime=repo/.furina-runtime → rejected."""
        repo = str(Path(__file__).resolve().parents[2])
        subdir = str(Path(__file__).resolve().parent)  # tests/e4/
        runtime = Path(repo) / ".furina-runtime-test"
        runtime.mkdir(exist_ok=True)
        try:
            exit_code = cli_main(["inspect", "prepare",
                                  "--workspace", subdir,
                                  "--runtime-dir", str(runtime)])
            assert exit_code == 1
        finally:
            runtime.rmdir()

    def test_subdirectory_workspace_allows_external_runtime(self, tmp_path):
        """workspace=repo/tests/e4, runtime=outside repo → allowed."""
        subdir = str(Path(__file__).resolve().parent)  # tests/e4/
        runtime = tmp_path / "external_runtime"
        runtime.mkdir()
        exit_code = cli_main(["inspect", "prepare",
                              "--workspace", subdir,
                              "--runtime-dir", str(runtime)])
        assert exit_code == 0


# === Section 2: G7 failure integration test ===

class TestG7FailureIntegration:
    def test_g7_failure_blocks_terminal(self, tmp_path, capsys):
        """Monkeypatched G7 failure must block terminal and return GATE_NOT_SATISFIED."""
        runtime = _prepare(tmp_path)
        capsys.readouterr()
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        # Monkeypatch evaluate_gate to fail only IL-G7
        original_evaluate_gate = evaluate_gate

        def patched_evaluate_gate(gate_id, *args, **kwargs):
            result = original_evaluate_gate(gate_id, *args, **kwargs)
            if gate_id == "IL-G7":
                return GateResult(
                    gate_id="IL-G7", outcome="fail",
                    checked_conditions=("injected failure",),
                    supporting_refs=result.supporting_refs,
                    failed_conditions=("injected G7 failure",),
                    checked_at=result.checked_at,
                )
            return result

        with patch("furina_code.cli.evaluate_gate", side_effect=patched_evaluate_gate):
            exit_code = cli_main(["inspect", "finalize",
                                  "--runtime-dir", str(runtime),
                                  "--run-binding-id", rb_id,
                                  "--candidate-file", cand_path])

        # Must fail
        assert exit_code != 0

        # Check stderr for GATE_NOT_SATISFIED
        stderr = capsys.readouterr().err
        err = json.loads(stderr)
        assert err["error"] == "GATE_NOT_SATISFIED"

        # Verify TaskRun is adjudicate/paused, NOT terminal
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()
        tr_events = [e for e in ledger.get_verified_events(rb_id)
                     if e["event_type"].startswith("TaskRun.")]
        tr_ref = tr_events[-1]["aggregate_ref"]
        tr_obj_id = tr_ref.split(":", 1)[1]
        _, tr_payload = ledger.get_latest("TaskRun", tr_obj_id)
        assert tr_payload["phase"] == "adjudicate"
        assert tr_payload["disposition"] == "paused"

        # No terminal TaskRun revision exists
        for evt in tr_events:
            _, p = ledger.get_latest("TaskRun", evt["aggregate_ref"].split(":", 1)[1])
            assert p["phase"] != "terminal"

        # No terminal Checkpoint
        cp_events = [e for e in ledger.get_verified_events(rb_id)
                     if e["event_type"].startswith("Checkpoint.")]
        for evt in cp_events:
            _, p = ledger.get_latest("Checkpoint", evt["aggregate_ref"].split(":", 1)[1])
            assert p["phase"] != "terminal"

        # G7 failed EvidenceEnvelope exists
        g7_events = [e for e in ledger.get_verified_events(rb_id)
                     if "gate:IL-G7" in e.get("aggregate_ref", "")]
        assert len(g7_events) > 0
        _, g7_payload = ledger.get_latest("EvidenceEnvelope",
                                          g7_events[0]["aggregate_ref"].split(":", 1)[1])
        assert g7_payload["integrity_status"] == "failed"

        # CompletionVerdict exists but didn't push to terminal
        cv_events = [e for e in ledger.get_verified_events(rb_id)
                     if e["event_type"].startswith("CompletionVerdict.")]
        assert len(cv_events) > 0

        ledger.close()


# === Section 3: G6 exact evidence mapping ===

class TestG6ExactEvidenceMapping:
    def test_g6_verifies_check_to_evidence_exact(self, tmp_path):
        """G6 must verify each check maps to exactly one evidence."""
        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])

        # Read verification evidence from ledger
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()

        # Get VerificationPlan
        vp_events = [e for e in ledger.get_verified_events(rb_id)
                     if e["event_type"].startswith("VerificationPlan.")]
        _, vp_payload = ledger.get_latest("VerificationPlan",
                                          vp_events[0]["aggregate_ref"].split(":", 1)[1])

        # Get VerificationVerdict
        vv_events = [e for e in ledger.get_verified_events(rb_id)
                     if e["event_type"].startswith("VerificationVerdict.")]
        _, vv_payload = ledger.get_latest("VerificationVerdict",
                                          vv_events[0]["aggregate_ref"].split(":", 1)[1])

        # Get verification evidence envelopes (filter by claim_scope)
        ev_events = [e for e in ledger.get_verified_events(rb_id)
                     if e["event_type"].startswith("EvidenceEnvelope.")]

        # Each check must have exactly one evidence
        check_to_ev = {}
        for evt in ev_events:
            obj_id = evt["aggregate_ref"].split(":", 1)[1]
            _, p = ledger.get_latest("EvidenceEnvelope", obj_id)
            if p["claim_scope"].startswith("verification:"):
                check = p["claim_scope"].split(":", 1)[1]
                check_to_ev[check] = obj_id

        # No missing checks
        for check in vp_payload["checks"]:
            assert check in check_to_ev, f"Check '{check}' has no evidence"

        # No extra evidence
        assert set(check_to_ev.keys()) == set(vp_payload["checks"])

        # Verdict refs equal the evidence set
        ev_refs = set()
        for check, ev_id in check_to_ev.items():
            meta, _ = ledger.get_latest("EvidenceEnvelope", ev_id)
            ev_refs.add(meta.integrity_ref)
        assert set(vv_payload["evidence_refs"]) == ev_refs

        ledger.close()


# === Section 4: G7 current head verification ===

class TestG7CurrentHeads:
    def test_g7_reads_current_heads_from_ledger(self, tmp_path):
        """G7 must verify objects are current Ledger heads."""
        runtime = _prepare(tmp_path)
        cand_path = write_candidate_file(runtime)
        rb_id = get_run_binding_id(runtime)

        cli_main(["inspect", "finalize",
                  "--runtime-dir", str(runtime),
                  "--run-binding-id", rb_id,
                  "--candidate-file", cand_path])

        # The real run passes G7, which means the current head check passed
        ledger = Ledger(str(runtime / "inspect.sqlite3"))
        ledger.open()

        # Verify CompletionVerdict is current head
        cv_head = ledger.get_head_revision("CompletionVerdict",
                                           [e for e in ledger.get_verified_events(rb_id)
                                            if e["event_type"].startswith("CompletionVerdict.")][0]
                                           ["aggregate_ref"].split(":", 1)[1])
        assert cv_head >= 1

        # Verify VerificationVerdict is current head
        vv_head = ledger.get_head_revision("VerificationVerdict",
                                           [e for e in ledger.get_verified_events(rb_id)
                                            if e["event_type"].startswith("VerificationVerdict.")][0]
                                           ["aggregate_ref"].split(":", 1)[1])
        assert vv_head >= 1

        ledger.close()

    def test_stale_completion_verdict_rejected(self):
        """G7 must reject stale CompletionVerdict."""
        # Create a mock CV at revision 1 but current head is revision 2
        from furina_code.contracts.objects import CompletionVerdict
        cv = CompletionVerdict.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_revision=1, task_run_ref="sha256:tr",
            verification_ref="sha256:vv",
            candidate_ref="sha256:ce", outcome="completed",
            completed_items=("c1",),
            no_project_side_effect=True,
            user_effect="No project files modified.",
        )
        # Simulate stale: current head ref differs
        current_heads = {"CompletionVerdict": "sha256:different_head"}
        gr = evaluate_gate("IL-G7", None, None, None, None, None, None, None, None, cv,
                           current_heads=current_heads)
        assert gr.outcome == "fail"
        assert any("not current head" in f for f in gr.failed_conditions)

    def test_stale_verification_verdict_rejected(self):
        """G7 must reject stale VerificationVerdict."""
        from furina_code.contracts.objects import CompletionVerdict, VerificationVerdict
        vv = VerificationVerdict.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            plan_ref="sha256:vp", evidence_refs=("sha256:ev",),
            criterion_results={"c1": "pass"}, coverage=1.0,
            outcome="pass", reason="all passed",
        )
        cv = CompletionVerdict.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_revision=1, task_run_ref="sha256:tr",
            verification_ref=vv.meta.integrity_ref,
            candidate_ref="sha256:ce", outcome="completed",
            completed_items=("c1",),
            no_project_side_effect=True,
            user_effect="No project files modified.",
        )
        current_heads = {
            "CompletionVerdict": cv.meta.integrity_ref,
            "VerificationVerdict": "sha256:different_vv_head",
        }
        gr = evaluate_gate("IL-G7", None, None, None, None, None, None, None, vv, cv,
                           current_heads=current_heads)
        assert gr.outcome == "fail"
        assert any("VerificationVerdict" in f and "not current head" in f for f in gr.failed_conditions)

    def test_g7_rejects_stale_task_run(self):
        """G7 must reject stale TaskRun."""
        from furina_code.contracts.objects import CompletionVerdict, TaskRun, Phase, Disposition
        from furina_code.contracts.meta import now_utc, SCHEMA_VERSION, compute_integrity_ref, CanonicalMeta
        now = now_utc()
        tr_meta_fields = {
            "schema_version": SCHEMA_VERSION, "object_type": "TaskRun", "object_id": "tr-1",
            "revision": 1, "owner_organ": "I2-D", "run_binding_id": "rb-1",
            "task_id": "t-1", "task_run_id": "tr-1", "project_ref": "p",
            "correlation_id": "c", "causation_ref": None,
            "created_at": now.isoformat(), "recorded_at": now.isoformat(),
            "classification": "project_internal", "supersedes_ref": None,
        }
        tr_payload = {"task_revision": 1, "phase": "terminal", "disposition": "terminal",
                      "current_refs": [], "open_requests": [],
                      "started_at": now.isoformat(), "terminal_reason": "completed"}
        tr_integrity = compute_integrity_ref(tr_meta_fields, tr_payload)
        tr_meta = CanonicalMeta(**{**tr_meta_fields, "integrity_ref": tr_integrity,
                                    "created_at": now, "recorded_at": now})
        tr = TaskRun(meta=tr_meta, task_revision=1, phase=Phase.TERMINAL,
                     disposition=Disposition.TERMINAL, current_refs=(), open_requests=(),
                     started_at=now, terminal_reason="completed")

        cv = CompletionVerdict.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_revision=1, task_run_ref=tr.meta.integrity_ref,
            verification_ref="sha256:vv",
            candidate_ref="sha256:ce", outcome="completed",
            completed_items=("c1",),
            no_project_side_effect=True,
            user_effect="No project files modified.",
        )
        current_heads = {
            "CompletionVerdict": cv.meta.integrity_ref,
            "VerificationVerdict": "sha256:vv",
            "TaskRun": "sha256:different_tr_head",
        }
        gr = evaluate_gate("IL-G7", None, None, None, None, None, None, None, None, cv,
                           task_run=tr, current_heads=current_heads)
        assert gr.outcome == "fail"
        assert any("TaskRun" in f and "not current head" in f for f in gr.failed_conditions)


# === Section 5: G6 failure tests ===

class TestG6FailureCases:
    def _make_vplan(self):
        from furina_code.contracts.objects import VerificationPlan
        return VerificationPlan.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            task_revision=1, candidate_ref="sha256:ce",
            success_criteria_map={"c1": "check-a", "c2": "check-b"},
            success_criteria=("c1", "c2"),
            checks=("check-a", "check-b"),
        )

    def _make_evidence(self, claim_scope, ref_suffix="ev1"):
        from furina_code.contracts.objects import EvidenceEnvelope
        return EvidenceEnvelope.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            claim_scope=claim_scope, evidence_type="existence_check",
            source_ref="test", claim="test claim",
            envelope_id=f"t-1:evidence:{ref_suffix}",
        )

    def _make_verdict(self, evidence_refs, coverage=1.0, outcome="pass"):
        return VerificationVerdict.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            plan_ref="sha256:vp", evidence_refs=evidence_refs,
            criterion_results={"c1": "pass", "c2": "pass"},
            coverage=coverage, outcome=outcome, reason="test",
        )

    def test_g6_fails_when_evidence_missing(self):
        """G6 must fail when a check has no evidence."""
        vplan = self._make_vplan()
        # Only provide evidence for check-a, not check-b
        ev_a = self._make_evidence("verification:check-a", "ev-a")
        vv = self._make_verdict(evidence_refs=(ev_a.meta.integrity_ref,))

        gr = evaluate_gate("IL-G6", None, None, None, None, None, None, vplan, vv, None,
                           verification_evidence=[ev_a])
        assert gr.outcome == "fail"
        assert any("check-b" in f and "no evidence" in f for f in gr.failed_conditions)

    def test_g6_fails_when_check_has_duplicate_evidence(self):
        """G6 must fail when a check has two or more evidence."""
        vplan = self._make_vplan()
        ev_a1 = self._make_evidence("verification:check-a", "ev-a1")
        ev_a2 = self._make_evidence("verification:check-a", "ev-a2")
        ev_b = self._make_evidence("verification:check-b", "ev-b")
        # Verdict refs all three
        vv = self._make_verdict(evidence_refs=(
            ev_a1.meta.integrity_ref, ev_a2.meta.integrity_ref, ev_b.meta.integrity_ref,
        ))

        gr = evaluate_gate("IL-G6", None, None, None, None, None, None, vplan, vv, None,
                           verification_evidence=[ev_a1, ev_a2, ev_b])
        assert gr.outcome == "fail"
        assert any("check-a" in f and "2 evidence" in f for f in gr.failed_conditions)

    def test_g6_fails_when_extra_verification_evidence_exists(self):
        """G6 must fail when evidence exists for checks not in plan."""
        vplan = self._make_vplan()
        ev_a = self._make_evidence("verification:check-a", "ev-a")
        ev_b = self._make_evidence("verification:check-b", "ev-b")
        ev_extra = self._make_evidence("verification:check-c", "ev-extra")
        vv = self._make_verdict(evidence_refs=(
            ev_a.meta.integrity_ref, ev_b.meta.integrity_ref, ev_extra.meta.integrity_ref,
        ))

        gr = evaluate_gate("IL-G6", None, None, None, None, None, None, vplan, vv, None,
                           verification_evidence=[ev_a, ev_b, ev_extra])
        assert gr.outcome == "fail"
        assert any("extra" in f.lower() and "check-c" in f for f in gr.failed_conditions)

    def test_g6_fails_when_verdict_refs_do_not_equal_required_set(self):
        """G6 must fail when verdict refs don't match required evidence set."""
        vplan = self._make_vplan()
        ev_a = self._make_evidence("verification:check-a", "ev-a")
        ev_b = self._make_evidence("verification:check-b", "ev-b")
        # Verdict missing ev_b
        vv = self._make_verdict(evidence_refs=(ev_a.meta.integrity_ref,))

        gr = evaluate_gate("IL-G6", None, None, None, None, None, None, vplan, vv, None,
                           verification_evidence=[ev_a, ev_b])
        assert gr.outcome == "fail"
        assert any("verdict" in f.lower() and "mismatch" in f.lower() for f in gr.failed_conditions)

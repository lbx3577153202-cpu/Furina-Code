"""E3.1 tests — concurrent revision conflict."""

import threading
import pytest
from furina_code.contracts import RunBinding, RevisionConflict
from furina_code.ledger import Ledger


def _make_binding(ledger, run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1"):
    obj = RunBinding.create(
        run_binding_id=run_binding_id, task_id=task_id, task_run_id=task_run_id,
        project_ref="p", correlation_id="c",
        subject_ref="u", user_ref="u", task_ref="t",
        allowed_tool_classes=(), source_refs=(),
    )
    ledger.write_object(obj.meta, {
        "subject_ref": obj.subject_ref, "user_ref": obj.user_ref,
        "project_ref": obj.project_ref, "task_ref": obj.task_ref,
        "allowed_tool_classes": [], "status": obj.status.value,
        "source_refs": [],
    }, caller_organ="I1-A", expected_revision=0)
    return obj


class TestConcurrentRevision:
    def test_concurrent_stale_write_rejected(self, tmp_path):
        """Two connections race to write revision 2 from revision 1.
        Exactly one succeeds; the other gets REVISION_CONFLICT.
        Head advances exactly once; event count is exactly 2.
        """
        db_path = str(tmp_path / "test.sqlite3")
        ledger1 = Ledger(db_path)
        ledger1.open()
        _make_binding(ledger1)
        ledger1.close()

        results: dict[str, Exception | None] = {"t1": None, "t2": None}
        barrier = threading.Barrier(2, timeout=10)

        def attempt(name: str):
            ledger = Ledger(db_path)
            ledger.open()
            try:
                # Build revision-2 meta with same stable fields as rev 1
                from furina_code.contracts.meta import CanonicalMeta, SCHEMA_VERSION, now_utc, compute_integrity_ref
                now = now_utc()
                supersedes = "RunBinding:rb-1:rev1"
                payload = {
                    "subject_ref": "u2", "user_ref": "u2",
                    "project_ref": "p", "task_ref": "t2",
                    "allowed_tool_classes": [], "status": "active", "source_refs": [],
                }
                meta_fields = {
                    "schema_version": SCHEMA_VERSION,
                    "object_type": "RunBinding",
                    "object_id": "rb-1",
                    "revision": 2,
                    "owner_organ": "I1-A",
                    "run_binding_id": "rb-1",
                    "task_id": "t-1",
                    "task_run_id": "tr-1",
                    "project_ref": "p",
                    "correlation_id": "c",
                    "causation_ref": supersedes,
                    "created_at": now.isoformat(),
                    "recorded_at": now.isoformat(),
                    "classification": "project_internal",
                    "supersedes_ref": supersedes,
                }
                integrity = compute_integrity_ref(meta_fields, payload)
                meta = CanonicalMeta(
                    schema_version=SCHEMA_VERSION,
                    object_type="RunBinding",
                    object_id="rb-1",
                    revision=2,
                    owner_organ="I1-A",
                    run_binding_id="rb-1",
                    task_id="t-1",
                    task_run_id="tr-1",
                    project_ref="p",
                    correlation_id="c",
                    causation_ref=supersedes,
                    created_at=now,
                    recorded_at=now,
                    classification="project_internal",
                    integrity_ref=integrity,
                    supersedes_ref=supersedes,
                )
                barrier.wait()  # synchronize both threads
                ledger.write_object(meta, payload, caller_organ="I1-A", expected_revision=1)
                results[name] = None  # success
            except RevisionConflict as exc:
                results[name] = exc
            except Exception as exc:
                results[name] = exc
            finally:
                ledger.close()

        t1 = threading.Thread(target=attempt, args=("t1",))
        t2 = threading.Thread(target=attempt, args=("t2",))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        successes = sum(1 for v in results.values() if v is None)
        conflicts = sum(1 for v in results.values() if isinstance(v, RevisionConflict))
        assert successes == 1, f"Expected 1 success, got {successes}: {results}"
        assert conflicts == 1, f"Expected 1 conflict, got {conflicts}: {results}"

        # Verify final state
        verify_ledger = Ledger(db_path)
        verify_ledger.open()
        assert verify_ledger.get_head_revision("RunBinding", "rb-1") == 2
        events = verify_ledger.get_events("rb-1")
        assert len(events) == 2
        revisions = {e["aggregate_revision"] for e in events}
        assert revisions == {1, 2}
        verify_ledger.close()

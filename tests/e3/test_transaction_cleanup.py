"""E3.2/E3.3 tests — transaction cleanup, contract error unification, TypeError evidence."""

import pytest
from furina_code.contracts import (
    RunBinding, ContractInvalid, LedgerWriteFailed, canonical_json_dumps,
)
from furina_code.ledger import Ledger


class TestTransactionCleanup:
    def test_nan_payload_raises_contract_invalid(self, tmp_path):
        """NaN in payload → CONTRACT_INVALID, not LEDGER_WRITE_FAILED."""
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()

        obj = RunBinding.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            subject_ref="u", user_ref="u", task_ref="t",
            allowed_tool_classes=(), source_refs=(),
        )
        payload_with_nan = {
            "subject_ref": "u", "user_ref": "u",
            "project_ref": "p", "task_ref": "t",
            "allowed_tool_classes": [], "status": "active",
            "source_refs": [],
            "bad_value": float("nan"),
        }
        with pytest.raises(ContractInvalid):
            ledger.write_object(obj.meta, payload_with_nan, caller_organ="I1-A", expected_revision=0)

        # Head must not be established
        assert ledger.get_head_revision("RunBinding", "rb-1") == 0
        # No events
        assert ledger.get_last_sequence() == 0
        ledger.close()

    def test_connection_reusable_after_nan_failure(self, tmp_path):
        """Ledger remains usable after a CONTRACT_INVALID failure."""
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()

        obj = RunBinding.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            subject_ref="u", user_ref="u", task_ref="t",
            allowed_tool_classes=(), source_refs=(),
        )
        bad_payload = {
            "subject_ref": "u", "user_ref": "u",
            "project_ref": "p", "task_ref": "t",
            "allowed_tool_classes": [], "status": "active",
            "source_refs": [],
            "bad": float("inf"),
        }
        with pytest.raises(ContractInvalid):
            ledger.write_object(obj.meta, bad_payload, caller_organ="I1-A", expected_revision=0)

        # Now write a valid object on the same ledger
        good_payload = {
            "subject_ref": "u", "user_ref": "u",
            "project_ref": "p", "task_ref": "t",
            "allowed_tool_classes": [], "status": "active",
            "source_refs": [],
        }
        ledger.write_object(obj.meta, good_payload, caller_organ="I1-A", expected_revision=0)
        assert ledger.get_head_revision("RunBinding", "rb-1") == 1
        ledger.close()

    def test_no_transaction_after_contract_invalid(self, tmp_path):
        """After CONTRACT_INVALID, connection.in_transaction must be False."""
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()

        obj = RunBinding.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            subject_ref="u", user_ref="u", task_ref="t",
            allowed_tool_classes=(), source_refs=(),
        )
        with pytest.raises(ContractInvalid):
            ledger.write_object(obj.meta, {"bad": float("nan"), "x": 1},
                                caller_organ="I1-A", expected_revision=0)

        assert not ledger.conn.in_transaction
        ledger.close()


class TestCanonicalJsonTypeError:
    def test_set_rejected_as_contract_invalid(self):
        """set() is not JSON-serializable → CONTRACT_INVALID, not bare TypeError."""
        with pytest.raises(ContractInvalid) as exc_info:
            canonical_json_dumps({"bad": {1, 2}})
        assert exc_info.value.code == "CONTRACT_INVALID"

    def test_custom_object_rejected_as_contract_invalid(self):
        """Custom non-serializable object → CONTRACT_INVALID, not bare TypeError."""
        class NotSerializable:
            pass
        with pytest.raises(ContractInvalid) as exc_info:
            canonical_json_dumps({"obj": NotSerializable()})
        assert exc_info.value.code == "CONTRACT_INVALID"


class TestCustomObjectTransactionCleanup:
    def test_custom_object_failure_cleans_transaction(self, tmp_path):
        """Non-serializable object in payload → CONTRACT_INVALID with full cleanup."""
        ledger = Ledger(str(tmp_path / "test.sqlite3"))
        ledger.open()

        obj = RunBinding.create(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            subject_ref="u", user_ref="u", task_ref="t",
            allowed_tool_classes=(), source_refs=(),
        )

        class NotSerializable:
            pass

        bad_payload = {
            "subject_ref": "u", "user_ref": "u",
            "project_ref": "p", "task_ref": "t",
            "allowed_tool_classes": [], "status": "active",
            "source_refs": [],
            "obj": NotSerializable(),
        }
        with pytest.raises(ContractInvalid):
            ledger.write_object(obj.meta, bad_payload, caller_organ="I1-A", expected_revision=0)

        # Transaction released
        assert not ledger.conn.in_transaction
        # No partial rows
        assert ledger.get_head_revision("RunBinding", "rb-1") == 0
        assert ledger.get_last_sequence() == 0

        # Connection reusable — write a valid object
        good_payload = {
            "subject_ref": "u", "user_ref": "u",
            "project_ref": "p", "task_ref": "t",
            "allowed_tool_classes": [], "status": "active",
            "source_refs": [],
        }
        ledger.write_object(obj.meta, good_payload, caller_organ="I1-A", expected_revision=0)
        assert ledger.get_head_revision("RunBinding", "rb-1") == 1
        events = ledger.get_events("rb-1")
        assert len(events) == 1
        ledger.close()

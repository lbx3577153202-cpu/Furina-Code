"""E4 shared test fixtures."""

import hashlib
import json
from pathlib import Path
from furina_code.ledger import Ledger
from furina_code.contracts.meta import canonical_json_dumps


def get_backend_profile_ref(runtime: Path) -> str:
    """Read the BackendProfile integrity_ref from the ledger."""
    ledger = Ledger(str(runtime / "inspect.sqlite3"))
    ledger.open()
    conn = ledger.conn
    cur = conn.execute("SELECT object_id FROM object_heads WHERE object_type='BackendProfile' LIMIT 1")
    row = cur.fetchone()
    if row:
        result = ledger.get_latest("BackendProfile", row[0])
        if result:
            meta, _ = result
            ledger.close()
            return meta.integrity_ref
    ledger.close()
    return "e4-repository-baseline-v1"


def get_context_digest(runtime: Path) -> str:
    """Read the real context_digest from the context packet file."""
    ctx_path = runtime / "context_packet.json"
    if not ctx_path.exists():
        return ""
    ctx_data = json.loads(ctx_path.read_text(encoding="utf-8"))
    # Recompute digest the same way write_context_packet does
    digest_input = {
        "schema_version": ctx_data.get("schema_version", "1.0"),
        "snapshot_ref": ctx_data.get("snapshot_ref"),
        "task_dossier_ref": ctx_data.get("task_dossier_ref"),
        "context_payload": ctx_data.get("context_payload"),
        "instruction_profile": ctx_data.get("instruction_profile"),
    }
    return "sha256:" + hashlib.sha256(
        canonical_json_dumps(digest_input).encode("utf-8")
    ).hexdigest()


def get_run_binding_id(runtime: Path) -> str:
    """Get the run_binding_id from the ledger."""
    ledger = Ledger(str(runtime / "inspect.sqlite3"))
    ledger.open()
    conn = ledger.conn
    cur = conn.execute("SELECT DISTINCT run_binding_id FROM event_envelopes LIMIT 1")
    row = cur.fetchone()
    ledger.close()
    return row[0] if row else ""


def get_task_run_id(runtime: Path) -> str:
    """Get the task_run_id from the ledger."""
    ledger = Ledger(str(runtime / "inspect.sqlite3"))
    ledger.open()
    conn = ledger.conn
    cur = conn.execute(
        "SELECT DISTINCT task_run_id FROM event_envelopes LIMIT 1"
    )
    row = cur.fetchone()
    ledger.close()
    return row[0] if row else ""


def get_candidate_drop_path(runtime: Path) -> str:
    """Compute the deterministic candidate drop path for a run."""
    rb_id = get_run_binding_id(runtime)
    tr_id = get_task_run_id(runtime)
    return str(runtime / "backend" / rb_id / tr_id / "candidate.json")


def write_candidate_file(runtime: Path, **content_overrides) -> str:
    """Write a valid candidate JSON file using prepare output data.

    Writes to the deterministic sandbox candidate path.
    """
    ctx_path = runtime / "context_packet.json"
    ctx_data = json.loads(ctx_path.read_text(encoding="utf-8"))
    snap = ctx_data.get("context_payload", {}).get("snapshot_summary", {})
    bp_ref = get_backend_profile_ref(runtime)
    ctx_digest = get_context_digest(runtime)

    content = {
        "repository_head": snap.get("head_sha", "a" * 40),
        "branch": snap.get("branch", "main"),
        "working_tree": "clean" if snap.get("is_clean", True) else "dirty",
        "tracked_file_count": snap.get("tracked_file_count", 0),
        "untracked_file_count": snap.get("untracked_file_count", 0),
        "python_requires": snap.get("requires_python"),
        "runtime_dependencies": snap.get("runtime_deps", []),
        "dev_dependencies": snap.get("dev_deps", []),
        "pytest_testpaths": snap.get("pytest_testpaths", []),
        "ci_config": {
            "present": snap.get("ci_config_exists", False),
            "sha256": snap.get("ci_config_sha256"),
        },
        "blind_spots": snap.get("blind_spots", []),
    }
    content.update(content_overrides)

    candidate = {
        "schema_version": "1.0",
        "candidate_type": "repository_baseline_report",
        "backend_profile_ref": bp_ref,
        "backend_session_ref": "test-session",
        "context_ref": ctx_data["context_envelope_ref"],
        "context_digest": ctx_digest,
        "content": content,
        "claimed_assumptions": [],
        "requested_actions": [],
    }
    cand_path = get_candidate_drop_path(runtime)
    Path(cand_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cand_path).write_text(json.dumps(candidate), encoding="utf-8")
    return cand_path

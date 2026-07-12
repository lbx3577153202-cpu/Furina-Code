"""Tests for BackendPort dependency boundary.

FileBackend must NOT import:
- ledger module
- CandidateEnvelope
- BackendProfile
- TaskRun
- CompletionVerdict
"""

import ast
from pathlib import Path


def _get_imports_from_file(filepath: Path) -> set[str]:
    """Extract all import names from a Python file using AST."""
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
                for alias in node.names:
                    imports.add(f"{node.module}.{alias.name}")
    return imports


class TestFileBackendDependencyBoundary:
    def test_no_ledger_import(self):
        """file_backend.py must not import ledger module."""
        imports = _get_imports_from_file(
            Path(__file__).resolve().parents[2] / "src" / "furina_code" / "backend" / "file_backend.py"
        )
        ledger_imports = {i for i in imports if "ledger" in i.lower()}
        assert not ledger_imports, f"file_backend.py imports ledger: {ledger_imports}"

    def test_no_candidate_envelope_import(self):
        """file_backend.py must not import CandidateEnvelope."""
        imports = _get_imports_from_file(
            Path(__file__).resolve().parents[2] / "src" / "furina_code" / "backend" / "file_backend.py"
        )
        ce_imports = {i for i in imports if "CandidateEnvelope" in i}
        assert not ce_imports, f"file_backend.py imports CandidateEnvelope: {ce_imports}"

    def test_no_backend_profile_import(self):
        """file_backend.py must not import BackendProfile."""
        imports = _get_imports_from_file(
            Path(__file__).resolve().parents[2] / "src" / "furina_code" / "backend" / "file_backend.py"
        )
        bp_imports = {i for i in imports if "BackendProfile" in i}
        assert not bp_imports, f"file_backend.py imports BackendProfile: {bp_imports}"

    def test_no_taskrun_import(self):
        """file_backend.py must not import TaskRun."""
        imports = _get_imports_from_file(
            Path(__file__).resolve().parents[2] / "src" / "furina_code" / "backend" / "file_backend.py"
        )
        tr_imports = {i for i in imports if "TaskRun" in i}
        assert not tr_imports, f"file_backend.py imports TaskRun: {tr_imports}"

    def test_no_completion_verdict_import(self):
        """file_backend.py must not import CompletionVerdict."""
        imports = _get_imports_from_file(
            Path(__file__).resolve().parents[2] / "src" / "furina_code" / "backend" / "file_backend.py"
        )
        cv_imports = {i for i in imports if "CompletionVerdict" in i}
        assert not cv_imports, f"file_backend.py imports CompletionVerdict: {cv_imports}"

    def test_port_has_no_ledger_import(self):
        """port.py must not import ledger module."""
        imports = _get_imports_from_file(
            Path(__file__).resolve().parents[2] / "src" / "furina_code" / "backend" / "port.py"
        )
        ledger_imports = {i for i in imports if "ledger" in i.lower()}
        assert not ledger_imports, f"port.py imports ledger: {ledger_imports}"

    def test_port_has_no_formal_object_import(self):
        """port.py must not import formal objects (CandidateEnvelope, BackendProfile, etc)."""
        imports = _get_imports_from_file(
            Path(__file__).resolve().parents[2] / "src" / "furina_code" / "backend" / "port.py"
        )
        formal_imports = {i for i in imports if any(
            name in i for name in ("CandidateEnvelope", "BackendProfile", "TaskRun",
                                    "CompletionVerdict", "Ledger")
        )}
        assert not formal_imports, f"port.py imports formal objects: {formal_imports}"

"""E4 tests — candidate file validation."""

import json
import pytest
from pathlib import Path
from furina_code.contracts import ContractInvalid
from furina_code.backend.candidate import (
    validate_candidate_file,
    validate_candidate_content,
    read_candidate_once,
    create_candidate_envelope,
)


class TestValidateCandidateFile:
    def test_valid_file(self, tmp_path):
        f = tmp_path / "candidate.json"
        f.write_text('{"test": true}')
        content, sha = validate_candidate_file(str(f))
        assert content == '{"test": true}'
        assert len(sha) == 64

    def test_missing_file(self, tmp_path):
        with pytest.raises(ContractInvalid):
            validate_candidate_file(str(tmp_path / "nonexistent.json"))

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text("")
        with pytest.raises(ContractInvalid):
            validate_candidate_file(str(f))

    def test_too_large(self, tmp_path):
        f = tmp_path / "large.json"
        f.write_bytes(b"x" * (11 * 1024 * 1024))
        with pytest.raises(ContractInvalid):
            validate_candidate_file(str(f))

    def test_symlink_rejected(self, tmp_path):
        target = tmp_path / "real.json"
        target.write_text('{"ok": true}')
        link = tmp_path / "link.json"
        link.symlink_to(target)
        with pytest.raises(ContractInvalid):
            validate_candidate_file(str(link))


class TestValidateCandidateContent:
    def _make_valid_candidate(self, context_ref="sha256:abc", context_digest="sha256:def", backend_ref="sha256:bp"):
        return json.dumps({
            "schema_version": "1.0",
            "candidate_type": "repository_baseline_report",
            "backend_profile_ref": backend_ref,
            "backend_session_ref": "session-1",
            "context_ref": context_ref,
            "context_digest": context_digest,
            "content": {
                "repository_head": "a" * 40,
                "branch": "main",
                "working_tree": "clean",
                "tracked_file_count": 10,
                "untracked_file_count": 0,
                "python_requires": ">=3.12",
                "runtime_dependencies": [],
                "dev_dependencies": ["pytest"],
                "pytest_testpaths": ["tests"],
                "ci_config": {"present": True, "sha256": "sha256:abc"},
                "blind_spots": [],
            },
            "claimed_assumptions": [],
            "requested_actions": [],
        })

    def test_valid_candidate(self):
        data = validate_candidate_content(
            self._make_valid_candidate(), "sha256:abc", "sha256:def", "sha256:bp"
        )
        assert data["schema_version"] == "1.0"

    def test_invalid_json(self):
        with pytest.raises(ContractInvalid):
            validate_candidate_content("not json", "sha256:abc", "sha256:def", "sha256:bp")

    def test_wrong_schema_version(self):
        content = self._make_valid_candidate().replace('"1.0"', '"2.0"')
        with pytest.raises(ContractInvalid):
            validate_candidate_content(content, "sha256:abc", "sha256:def", "sha256:bp")

    def test_wrong_candidate_type(self):
        content = self._make_valid_candidate().replace("repository_baseline_report", "unknown")
        with pytest.raises(ContractInvalid):
            validate_candidate_content(content, "sha256:abc", "sha256:def", "sha256:bp")

    def test_context_ref_mismatch(self):
        with pytest.raises(ContractInvalid):
            validate_candidate_content(self._make_valid_candidate(), "sha256:WRONG", "sha256:def", "sha256:bp")

    def test_context_digest_mismatch(self):
        with pytest.raises(ContractInvalid):
            validate_candidate_content(self._make_valid_candidate(), "sha256:abc", "sha256:WRONG", "sha256:bp")

    def test_missing_context_digest(self):
        content = self._make_valid_candidate()
        parsed = json.loads(content)
        del parsed["context_digest"]
        with pytest.raises(ContractInvalid):
            validate_candidate_content(json.dumps(parsed), "sha256:abc", "sha256:def", "sha256:bp")

    def test_backend_ref_mismatch(self):
        with pytest.raises(ContractInvalid):
            validate_candidate_content(self._make_valid_candidate(), "sha256:abc", "sha256:def", "sha256:WRONG")

    def test_nonempty_requested_actions(self):
        content = self._make_valid_candidate().replace('"requested_actions": []', '"requested_actions": ["x"]')
        with pytest.raises(ContractInvalid):
            validate_candidate_content(content, "sha256:abc", "sha256:def", "sha256:bp")

    def test_missing_content_section(self):
        content = json.dumps({
            "schema_version": "1.0",
            "candidate_type": "repository_baseline_report",
            "backend_profile_ref": "sha256:bp",
            "backend_session_ref": "s",
            "context_ref": "sha256:abc",
            "context_digest": "sha256:def",
            "claimed_assumptions": [],
            "requested_actions": [],
        })
        with pytest.raises(ContractInvalid):
            validate_candidate_content(content, "sha256:abc", "sha256:def", "sha256:bp")

    def test_content_not_object(self):
        content = json.dumps({
            "schema_version": "1.0",
            "candidate_type": "repository_baseline_report",
            "backend_profile_ref": "sha256:bp",
            "backend_session_ref": "s",
            "context_ref": "sha256:abc",
            "context_digest": "sha256:def",
            "content": "not an object",
            "claimed_assumptions": [],
            "requested_actions": [],
        })
        with pytest.raises(ContractInvalid):
            validate_candidate_content(content, "sha256:abc", "sha256:def", "sha256:bp")

    def test_requested_actions_not_list(self):
        content = json.dumps({
            "schema_version": "1.0",
            "candidate_type": "repository_baseline_report",
            "backend_profile_ref": "sha256:bp",
            "backend_session_ref": "s",
            "context_ref": "sha256:abc",
            "context_digest": "sha256:def",
            "content": {"repository_head": "a" * 40, "branch": "main", "working_tree": "clean",
                        "tracked_file_count": 0, "untracked_file_count": 0, "python_requires": None,
                        "runtime_dependencies": [], "dev_dependencies": [], "pytest_testpaths": [],
                        "ci_config": {"present": False}, "blind_spots": []},
            "claimed_assumptions": [],
            "requested_actions": "not a list",
        })
        with pytest.raises(ContractInvalid):
            validate_candidate_content(content, "sha256:abc", "sha256:def", "sha256:bp")

    def test_claimed_assumptions_not_string_list(self):
        content = json.dumps({
            "schema_version": "1.0",
            "candidate_type": "repository_baseline_report",
            "backend_profile_ref": "sha256:bp",
            "backend_session_ref": "s",
            "context_ref": "sha256:abc",
            "context_digest": "sha256:def",
            "content": {"repository_head": "a" * 40, "branch": "main", "working_tree": "clean",
                        "tracked_file_count": 0, "untracked_file_count": 0, "python_requires": None,
                        "runtime_dependencies": [], "dev_dependencies": [], "pytest_testpaths": [],
                        "ci_config": {"present": False}, "blind_spots": []},
            "claimed_assumptions": [123],
            "requested_actions": [],
        })
        with pytest.raises(ContractInvalid):
            validate_candidate_content(content, "sha256:abc", "sha256:def", "sha256:bp")

    def test_wrong_field_type(self):
        content = json.dumps({
            "schema_version": "1.0",
            "candidate_type": "repository_baseline_report",
            "backend_profile_ref": "sha256:bp",
            "backend_session_ref": "s",
            "context_ref": "sha256:abc",
            "context_digest": "sha256:def",
            "content": {"repository_head": 12345, "branch": "main", "working_tree": "clean",
                        "tracked_file_count": 0, "untracked_file_count": 0, "python_requires": None,
                        "runtime_dependencies": [], "dev_dependencies": [], "pytest_testpaths": [],
                        "ci_config": {"present": False}, "blind_spots": []},
            "claimed_assumptions": [],
            "requested_actions": [],
        })
        with pytest.raises(ContractInvalid):
            validate_candidate_content(content, "sha256:abc", "sha256:def", "sha256:bp")


class TestCreateCandidateEnvelope:
    def test_create(self, tmp_path):
        f = tmp_path / "candidate.json"
        f.write_text('{"schema_version": "1.0"}')
        _, _, sha = read_candidate_once(str(f))
        ce = create_candidate_envelope(
            run_binding_id="rb-1", task_id="t-1", task_run_id="tr-1",
            project_ref="p", correlation_id="c",
            candidate_type="repository_baseline_report",
            backend_profile_ref="sha256:bp",
            backend_session_ref="session-1",
            context_ref="sha256:ctx",
            content_ref="sha256:ct",
            candidate_digest=sha,
        )
        assert ce.meta.object_type == "CandidateEnvelope"
        assert len(ce.candidate_digest) == 64

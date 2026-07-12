"""Furina Code backend — MiMo Code CLI adapter.

Implements the BackendPort protocol using the MiMo CLI (`mimo run`).
Does NOT create CandidateEnvelope, write Ledger, or transition TaskRun.
Does NOT import ledger, formal objects factories, or orchestration modules.

Each invocation:
- creates a fresh temporary CWD outside the repository
- never passes --continue
- captures bounded stdout/stderr via temp files (not in-memory)
- validates structured output, not just exit code
- writes candidate to persistent runtime sandbox
- cleans up temporary CWD and output files
"""

from __future__ import annotations

import dataclasses
import hashlib
import json as _json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ..contracts.errors import ContractInvalid
from .port import (
    BackendInvocationPlan,
    BackendInvocationRequest,
    BackendProbeRequest,
    BackendProbeResult,
    BackendTransportResult,
    TransportStatus,
    compute_empty_args_digest,
    verify_backend_request_digest,
)

_ERROR_MESSAGES: dict[str, str] = {
    "executable_not_found": "MiMo executable not found on PATH.",
    "launch_failed": "Failed to launch MiMo process.",
    "timeout_expired": "MiMo process exceeded timeout.",
    "process_tree_terminated": "MiMo process and children were terminated.",
    "output_too_large": "MiMo output exceeded size limit.",
    "invalid_utf8": "MiMo output is not valid UTF-8.",
    "protocol_error": "MiMo output is not valid JSON or missing expected fields.",
    "provider_error": "MiMo reported a provider or model error.",
    "nonzero_exit": "MiMo process exited with non-zero status.",
    "candidate_write_failed": "Failed to write candidate file to sandbox.",
    "sandbox_violation": "Sandbox path is outside allowed boundaries.",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_json_dumps(obj: object) -> str:
    """Canonical JSON for digests."""
    return _json.dumps(obj, sort_keys=True, separators=(",", ":"))


class MiMoCodeCLIAdapter:
    """BackendPort implementation using the MiMo CLI.

    Constructor takes:
    - runtime_root: trusted directory for candidate persistence
    - mimo_executable: path/name of mimo binary
    - forbidden_roots: directories that must not overlap with runtime_root
    """

    def __init__(
        self,
        *,
        runtime_root: Path,
        mimo_executable: str = "mimo",
        default_model: str | None = None,
        forbidden_roots: tuple[Path, ...] = (),
    ) -> None:
        self._runtime_root = Path(runtime_root)
        self._mimo_executable = mimo_executable
        self._default_model = default_model
        self._forbidden_roots = tuple(Path(r) for r in forbidden_roots)

    def probe(self, request: BackendProbeRequest) -> BackendProbeResult:
        errors: list[str] = []

        # Check runtime root
        if not self._runtime_root.exists() or not self._runtime_root.is_dir():
            errors.append("sandbox_violation")

        # Check executable
        try:
            result = subprocess.run(
                [self._mimo_executable, "--version"],
                capture_output=True, text=True, timeout=10,
                shell=False,
            )
            version = result.stdout.strip() if result.returncode == 0 else None
            if result.returncode != 0:
                errors.append("executable_not_found")
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            errors.append("executable_not_found")
            version = None

        return BackendProbeResult(
            available=len(errors) == 0,
            version=version,
            executable_ref=request.executable_ref,
            supported_flags=("format", "model"),
            model_ids=(),
            errors=tuple(errors),
        )

    def prepare(self, request: BackendInvocationRequest) -> BackendInvocationPlan:
        verify_backend_request_digest(request)

        args: list[str] = [
            self._mimo_executable,
            "run",
            request.instruction_text,
            "--format", "json",
        ]
        if request.model_ref:
            args.extend(["--model", request.model_ref])

        return BackendInvocationPlan(
            request=request,
            executable_args=tuple(args),
            cwd_ref=request.sandbox_path_ref,
            env_policy_ref="mimo-cli:inherit",
            env_key_allowlist=(),
            credential_mode="inherit",
            provider_state_policy_ref="mimo-cli:fresh-session",
        )

    def invoke(self, plan: BackendInvocationPlan) -> BackendTransportResult:
        request = plan.request

        # Validate candidate path BEFORE launching process
        try:
            self._resolve_candidate_path(request)
        except ContractInvalid:
            return self._error_result(
                request, TransportStatus.SANDBOX_VIOLATION,
                "sandbox_violation",
            )

        # Create fresh temp CWD
        temp_cwd = Path(tempfile.mkdtemp(prefix="furina_mimo_"))
        # Temp output files (cleaned up with temp_cwd)
        stdout_file = temp_cwd / "stdout.bin"
        stderr_file = temp_cwd / "stderr.bin"

        temp_cwd_resolved = temp_cwd.resolve()
        for forbidden in self._forbidden_roots:
            try:
                temp_cwd_resolved.relative_to(forbidden.resolve())
                shutil.rmtree(temp_cwd, ignore_errors=True)
                return self._error_result(
                    request, TransportStatus.SANDBOX_VIOLATION,
                    "sandbox_violation",
                )
            except ValueError:
                pass

        started_at = _now_iso()
        timeout = max(request.timeout_seconds, 1) if request.timeout_seconds > 0 else 300
        max_stdout = request.max_stdout_bytes
        max_stderr = request.max_stderr_bytes

        # Compute command_args_digest from actual args
        args_digest = _sha256_bytes(
            _canonical_json_dumps(list(plan.executable_args)).encode("utf-8")
        )

        try:
            return self._run_process(
                plan, temp_cwd, stdout_file, stderr_file,
                started_at, max_stdout, max_stderr, timeout, args_digest,
            )
        finally:
            shutil.rmtree(temp_cwd, ignore_errors=True)

    def _run_process(
        self,
        plan: BackendInvocationPlan,
        temp_cwd: Path,
        stdout_file: Path,
        stderr_file: Path,
        started_at: str,
        max_stdout: int,
        max_stderr: int,
        timeout: int,
        args_digest: str,
    ) -> BackendTransportResult:
        request = plan.request
        args = list(plan.executable_args)

        # Launch with file-based capture
        with open(stdout_file, "wb") as fout, open(stderr_file, "wb") as ferr:
            try:
                popen_kwargs: dict = dict(
                    stdout=fout,
                    stderr=ferr,
                    cwd=str(temp_cwd),
                    shell=False,
                )
                if sys.platform == "win32":
                    popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                else:
                    popen_kwargs["start_new_session"] = True

                proc = subprocess.Popen(args, **popen_kwargs)
            except FileNotFoundError:
                return self._error_result(
                    request, TransportStatus.LAUNCH_FAILED,
                    "executable_not_found",
                )
            except OSError:
                return self._error_result(
                    request, TransportStatus.LAUNCH_FAILED,
                    "launch_failed",
                )

            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._kill_process_tree(proc)
                proc.wait()
                finished_at = _now_iso()
                stdout_bytes, stderr_bytes = self._read_captured_files(
                    stdout_file, stderr_file, max_stdout + 1, max_stderr + 1,
                )
                return self._build_timeout_result(
                    request, started_at, finished_at,
                    stdout_bytes, stderr_bytes, max_stdout, max_stderr,
                    args_digest,
                )

            finished_at = _now_iso()
            exit_code = proc.returncode

        # Read captured files
        stdout_bytes, stderr_bytes = self._read_captured_files(
            stdout_file, stderr_file, max_stdout + 1, max_stderr + 1,
        )

        stdout_exceeded = len(stdout_bytes) > max_stdout
        stderr_exceeded = len(stderr_bytes) > max_stderr

        # Fail-closed on overflow
        if stdout_exceeded:
            return self._overflow_result(
                request, started_at, finished_at,
                stdout_bytes, stderr_bytes, max_stdout, max_stderr,
                "stdout", args_digest,
            )
        if stderr_exceeded:
            return self._overflow_result(
                request, started_at, finished_at,
                stdout_bytes, stderr_bytes, max_stdout, max_stderr,
                "stderr", args_digest,
            )

        # Non-zero exit
        if exit_code != 0:
            stderr_text = self._safe_decode(stderr_bytes)
            error_code, error_detail = self._classify_stderr(stderr_text)
            return self._make_result(
                request,
                transport_status=TransportStatus.NONZERO_EXIT.value,
                error_code=error_code,
                error_detail=error_detail,
                started_at=started_at,
                finished_at=finished_at,
                stdout_bytes=stdout_bytes, max_stdout=max_stdout,
                stderr_bytes=stderr_bytes, max_stderr=max_stderr,
                args_digest=args_digest,
            )

        # Exit 0 — parse JSON
        stdout_text = self._safe_decode(stdout_bytes)
        if stdout_text is None:
            return self._make_result(
                request,
                transport_status=TransportStatus.INVALID_UTF8.value,
                error_code="invalid_utf8",
                error_detail=_ERROR_MESSAGES["invalid_utf8"],
                started_at=started_at, finished_at=finished_at,
                stdout_bytes=stdout_bytes, max_stdout=max_stdout,
                stderr_bytes=stderr_bytes, max_stderr=max_stderr,
                args_digest=args_digest,
            )

        parsed_lines = self._parse_jsonl(stdout_text)
        if parsed_lines is None:
            return self._make_result(
                request,
                transport_status=TransportStatus.PROTOCOL_ERROR.value,
                error_code="protocol_error",
                error_detail=_ERROR_MESSAGES["protocol_error"],
                started_at=started_at, finished_at=finished_at,
                stdout_bytes=stdout_bytes, max_stdout=max_stdout,
                stderr_bytes=stderr_bytes, max_stderr=max_stderr,
                args_digest=args_digest,
            )

        stderr_text = self._safe_decode(stderr_bytes) or ""
        if self._has_provider_error(stderr_text, parsed_lines):
            error_code, error_detail = self._classify_stderr(stderr_text)
            return self._make_result(
                request,
                transport_status=TransportStatus.PROTOCOL_ERROR.value,
                error_code=error_code, error_detail=error_detail,
                started_at=started_at, finished_at=finished_at,
                stdout_bytes=stdout_bytes, max_stdout=max_stdout,
                stderr_bytes=stderr_bytes, max_stderr=max_stderr,
                args_digest=args_digest,
            )

        text_content = self._extract_text(parsed_lines)
        if not text_content:
            return self._make_result(
                request,
                transport_status=TransportStatus.PROTOCOL_ERROR.value,
                error_code="protocol_error",
                error_detail="MiMo produced no text output.",
                started_at=started_at, finished_at=finished_at,
                stdout_bytes=stdout_bytes, max_stdout=max_stdout,
                stderr_bytes=stderr_bytes, max_stderr=max_stderr,
                args_digest=args_digest,
            )

        # Extract session ID
        session_id = None
        for line in parsed_lines:
            if isinstance(line, dict) and "sessionID" in line:
                session_id = line["sessionID"]
                break

        # Build and write candidate to persistent sandbox
        candidate = self._build_candidate(request, text_content)
        candidate_bytes = _json.dumps(candidate, ensure_ascii=False).encode("utf-8")

        try:
            candidate_path = self._resolve_candidate_path(request)
        except ContractInvalid as exc:
            return self._make_result(
                request,
                transport_status=TransportStatus.SANDBOX_VIOLATION.value,
                error_code="sandbox_violation",
                error_detail=str(exc),
                started_at=started_at, finished_at=finished_at,
                stdout_bytes=stdout_bytes, max_stdout=max_stdout,
                stderr_bytes=stderr_bytes, max_stderr=max_stderr,
                args_digest=args_digest,
            )
        try:
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path.write_bytes(candidate_bytes)
        except OSError:
            return self._make_result(
                request,
                transport_status=TransportStatus.AMBIGUOUS.value,
                error_code="candidate_write_failed",
                error_detail=_ERROR_MESSAGES["candidate_write_failed"],
                started_at=started_at, finished_at=finished_at,
                stdout_bytes=stdout_bytes, max_stdout=max_stdout,
                stderr_bytes=stderr_bytes, max_stderr=max_stderr,
                args_digest=args_digest,
            )

        return self._make_result(
            request,
            transport_status=TransportStatus.SUCCEEDED.value,
            error_code=None, error_detail=None,
            started_at=started_at, finished_at=finished_at,
            stdout_bytes=stdout_bytes, max_stdout=max_stdout,
            stderr_bytes=stderr_bytes, max_stderr=max_stderr,
            candidate_ref=f"{request.sandbox_path_ref}/candidate.json",
            candidate_digest=_sha256_bytes(candidate_bytes),
            provider_session_ref=session_id,
            args_digest=args_digest,
        )

    def collect(
        self,
        plan: BackendInvocationPlan,
        transport: BackendTransportResult,
    ) -> BackendTransportResult:
        """Collect re-reads the persisted candidate and binds digest."""
        if transport.transport_status != TransportStatus.SUCCEEDED.value:
            return transport

        request = plan.request
        try:
            candidate_path = self._resolve_candidate_path(request)
        except ContractInvalid:
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.SANDBOX_VIOLATION.value,
                error_code="sandbox_violation",
                error_detail="Invalid candidate path.",
                finished_at=_now_iso(),
            )

        if not candidate_path.exists():
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.AMBIGUOUS.value,
                error_code="candidate_evidence_mismatch",
                error_detail="Candidate file not found after invoke.",
                finished_at=_now_iso(),
            )

        try:
            raw = candidate_path.read_bytes()
        except OSError:
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.AMBIGUOUS.value,
                error_code="candidate_evidence_mismatch",
                error_detail="Failed to read candidate file.",
                finished_at=_now_iso(),
            )

        actual_digest = _sha256_bytes(raw)
        if actual_digest != transport.candidate_digest:
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.AMBIGUOUS.value,
                error_code="candidate_evidence_mismatch",
                error_detail="Candidate file changed after write.",
                finished_at=_now_iso(),
            )

        return transport

    def strict_validate(
        self,
        request: BackendInvocationRequest,
        transport: BackendTransportResult,
    ) -> BackendTransportResult:
        if transport.transport_status != TransportStatus.SUCCEEDED.value:
            return transport

        if not transport.candidate_ref or not transport.candidate_digest:
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.AMBIGUOUS.value,
                error_code="candidate_evidence_mismatch",
                error_detail="Missing candidate ref or digest.",
                finished_at=_now_iso(),
            )

        if transport.request_digest != request.request_digest:
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.AMBIGUOUS.value,
                error_code="candidate_evidence_mismatch",
                error_detail="Request digest mismatch.",
                finished_at=_now_iso(),
            )

        # Re-read the persisted candidate and verify
        try:
            candidate_path = self._resolve_candidate_path(request)
        except ContractInvalid:
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.SANDBOX_VIOLATION.value,
                error_code="sandbox_violation",
                error_detail="Invalid candidate path during validation.",
                finished_at=_now_iso(),
            )
        if not candidate_path.exists():
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.AMBIGUOUS.value,
                error_code="candidate_evidence_mismatch",
                error_detail="Candidate file not found during validation.",
                finished_at=_now_iso(),
            )

        try:
            raw = candidate_path.read_bytes()
        except OSError:
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.AMBIGUOUS.value,
                error_code="candidate_evidence_mismatch",
                error_detail="Failed to read candidate during validation.",
                finished_at=_now_iso(),
            )

        actual_digest = _sha256_bytes(raw)
        if actual_digest != transport.candidate_digest:
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.AMBIGUOUS.value,
                error_code="candidate_evidence_mismatch",
                error_detail="Candidate file digest changed since collection.",
                finished_at=_now_iso(),
            )

        return transport

    # --- Internal helpers ---

    def _resolve_candidate_path(self, request: BackendInvocationRequest) -> Path:
        ref = request.sandbox_path_ref
        if not ref:
            raise ContractInvalid("Sandbox path ref must not be empty.")
        relative_ref = Path(ref)
        if relative_ref.is_absolute() or ".." in relative_ref.parts:
            raise ContractInvalid(
                "MIMO_SANDBOX_PATH_INVALID",
                {"sandbox_path_ref": ref},
            )

        runtime_root = self._runtime_root.resolve()
        sandbox = (runtime_root / relative_ref).resolve()
        candidate = (sandbox / "candidate.json").resolve()

        # Candidate must be inside runtime_root
        try:
            candidate.relative_to(runtime_root)
        except ValueError:
            raise ContractInvalid(
                "MIMO_SANDBOX_PATH_ESCAPE",
                {"candidate": str(candidate), "runtime_root": str(runtime_root)},
            )

        # Candidate must not be inside any forbidden root
        for forbidden in self._forbidden_roots:
            forbidden_resolved = forbidden.resolve()
            try:
                candidate.relative_to(forbidden_resolved)
            except ValueError:
                continue
            raise ContractInvalid(
                "MIMO_SANDBOX_FORBIDDEN_ROOT",
                {"candidate": str(candidate), "forbidden": str(forbidden_resolved)},
            )

        return candidate

    @staticmethod
    def _kill_process_tree(proc: subprocess.Popen) -> None:
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True, timeout=5,
                )
            else:
                import signal
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    @staticmethod
    def _safe_decode(data: bytes) -> str | None:
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    @staticmethod
    def _parse_jsonl(text: str) -> list[dict] | None:
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = _json.loads(line)
                if isinstance(obj, dict):
                    lines.append(obj)
            except _json.JSONDecodeError:
                return None
        return lines if lines else None

    @staticmethod
    def _extract_text(events: list[dict]) -> str | None:
        for event in events:
            if event.get("type") == "text":
                part = event.get("part", {})
                text = part.get("text")
                if text:
                    return text
        return None

    @staticmethod
    def _has_provider_error(stderr_text: str, events: list[dict]) -> bool:
        for indicator in ("Error:", "error:", "ProviderModelNotFoundError",
                          "not found", "failed", "authentication"):
            if indicator in stderr_text:
                return True
        return False

    @staticmethod
    def _classify_stderr(stderr_text: str) -> tuple[str, str]:
        lower = stderr_text.lower()
        if "model not found" in lower or "providernotfounderror" in lower:
            return "provider_error", "MiMo reported model not found."
        if "authentication" in lower or "unauthorized" in lower:
            return "provider_error", "MiMo reported authentication failure."
        if "timeout" in lower:
            return "timeout_expired", _ERROR_MESSAGES["timeout_expired"]
        return "nonzero_exit", _ERROR_MESSAGES["nonzero_exit"]

    @staticmethod
    def _read_captured_files(
        stdout_file: Path, stderr_file: Path,
        max_stdout: int, max_stderr: int,
    ) -> tuple[bytes, bytes]:
        """Read captured output files with hard limits (max+1 bytes)."""
        stdout_bytes = b""
        stderr_bytes = b""
        try:
            with open(stdout_file, "rb") as f:
                stdout_bytes = f.read(max_stdout)
        except OSError:
            pass
        try:
            with open(stderr_file, "rb") as f:
                stderr_bytes = f.read(max_stderr)
        except OSError:
            pass
        return stdout_bytes, stderr_bytes

    @staticmethod
    def _build_candidate(
        request: BackendInvocationRequest, text_content: str,
    ) -> dict:
        """Parse model output as strict JSON and build candidate with trusted bindings.

        The model MUST return a JSON object with valid content fields.
        Raw text fallback is not allowed — any parse failure is protocol_error.
        """
        try:
            parsed = _json.loads(text_content)
        except (_json.JSONDecodeError, ValueError) as exc:
            raise ContractInvalid(
                "MIMO_OUTPUT_INVALID_JSON",
                {"detail": str(exc)},
            )

        if not isinstance(parsed, dict):
            raise ContractInvalid(
                "MIMO_OUTPUT_NOT_OBJECT",
                {"detail": "Model output must be a JSON object."},
            )

        # Strict field validation
        _REQUIRED_CONTENT_FIELDS = {
            "repository_head": str,
            "branch": str,
            "working_tree": str,
            "tracked_file_count": int,
            "untracked_file_count": int,
            "python_requires": (str, type(None)),
            "runtime_dependencies": list,
            "dev_dependencies": list,
            "pytest_testpaths": list,
            "ci_config": dict,
            "blind_spots": list,
        }

        for field, expected_type in _REQUIRED_CONTENT_FIELDS.items():
            if field not in parsed:
                raise ContractInvalid(
                    "MIMO_OUTPUT_MISSING_FIELD",
                    {"field": field},
                )
            if not isinstance(parsed[field], expected_type):
                raise ContractInvalid(
                    "MIMO_OUTPUT_WRONG_TYPE",
                    {"field": field, "expected": expected_type.__name__ if not isinstance(expected_type, tuple) else "/".join(t.__name__ for t in expected_type)},
                )

        # Validate working_tree value
        if parsed["working_tree"] not in ("clean", "dirty"):
            raise ContractInvalid(
                "MIMO_OUTPUT_INVALID_WORKING_TREE",
                {"value": parsed["working_tree"]},
            )

        # Validate ci_config structure
        ci_config = parsed["ci_config"]
        if "present" not in ci_config or not isinstance(ci_config["present"], bool):
            raise ContractInvalid(
                "MIMO_OUTPUT_INVALID_CI_CONFIG",
                {"detail": "ci_config must have 'present' (bool)"},
            )

        # Validate list element types
        for field in ("runtime_dependencies", "dev_dependencies", "pytest_testpaths", "blind_spots"):
            for i, item in enumerate(parsed[field]):
                if not isinstance(item, str):
                    raise ContractInvalid(
                        "MIMO_OUTPUT_WRONG_ELEMENT_TYPE",
                        {"field": field, "index": i},
                    )

        return {
            "schema_version": "1.0",
            "candidate_type": "repository_baseline_report",
            "backend_profile_ref": request.backend_profile_ref,
            "backend_session_ref": request.backend_session_ref,
            "context_ref": request.context_ref,
            "context_digest": request.context_digest,
            "content": parsed,
            "claimed_assumptions": [],
            "requested_actions": [],
        }

    def _make_result(
        self, request, *, transport_status, error_code, error_detail,
        started_at, finished_at,
        stdout_bytes=b"", max_stdout=10_000_000,
        stderr_bytes=b"", max_stderr=1_000_000,
        candidate_ref=None, candidate_digest=None,
        provider_session_ref=None, args_digest=None,
    ) -> BackendTransportResult:
        stdout_truncated = len(stdout_bytes) > max_stdout
        stderr_truncated = len(stderr_bytes) > max_stderr
        return BackendTransportResult(
            invocation_id=request.invocation_id,
            request_digest=request.request_digest,
            backend_session_ref=request.backend_session_ref,
            provider_session_ref=provider_session_ref,
            provider_ref="mimo-cli",
            executable_version="mimo-cli-1.0",
            started_at=started_at, finished_at=finished_at,
            command_args_digest=args_digest or compute_empty_args_digest(),
            stdout_ref=None,
            stdout_digest=_sha256_bytes(stdout_bytes[:max_stdout]) if stdout_bytes else None,
            stdout_bytes=len(stdout_bytes), stdout_truncated=stdout_truncated,
            stderr_ref=None,
            stderr_digest=_sha256_bytes(stderr_bytes[:max_stderr]) if stderr_bytes else None,
            stderr_bytes=len(stderr_bytes), stderr_truncated=stderr_truncated,
            candidate_ref=candidate_ref, candidate_digest=candidate_digest,
            manifest_before_ref=None, manifest_before_digest=None,
            manifest_after_ref=None, manifest_after_digest=None,
            transport_status=transport_status,
            error_code=error_code, error_detail=error_detail,
        )

    def _error_result(self, request, status, error_code):
        return BackendTransportResult(
            invocation_id=request.invocation_id,
            request_digest=request.request_digest,
            backend_session_ref=request.backend_session_ref,
            provider_session_ref=None,
            provider_ref="mimo-cli", executable_version="mimo-cli-1.0",
            started_at=_now_iso(), finished_at=_now_iso(),
            command_args_digest=compute_empty_args_digest(),
            stdout_ref=None, stdout_digest=None, stdout_bytes=0, stdout_truncated=False,
            stderr_ref=None, stderr_digest=None, stderr_bytes=0, stderr_truncated=False,
            candidate_ref=None, candidate_digest=None,
            manifest_before_ref=None, manifest_before_digest=None,
            manifest_after_ref=None, manifest_after_digest=None,
            transport_status=status.value,
            error_code=error_code,
            error_detail=_ERROR_MESSAGES.get(error_code, "Unknown error."),
        )

    def _build_timeout_result(
        self, request, started_at, finished_at,
        stdout_bytes, stderr_bytes, max_stdout, max_stderr, args_digest,
    ):
        return self._make_result(
            request,
            transport_status=TransportStatus.TIMEOUT.value,
            error_code="timeout_expired",
            error_detail=_ERROR_MESSAGES["timeout_expired"],
            started_at=started_at, finished_at=finished_at,
            stdout_bytes=stdout_bytes, max_stdout=max_stdout,
            stderr_bytes=stderr_bytes, max_stderr=max_stderr,
            args_digest=args_digest,
        )

    def _overflow_result(
        self, request, started_at, finished_at,
        stdout_bytes, stderr_bytes, max_stdout, max_stderr,
        which, args_digest,
    ):
        return self._make_result(
            request,
            transport_status=TransportStatus.OUTPUT_TOO_LARGE.value,
            error_code="output_too_large",
            error_detail=_ERROR_MESSAGES["output_too_large"],
            started_at=started_at, finished_at=finished_at,
            stdout_bytes=stdout_bytes, max_stdout=max_stdout,
            stderr_bytes=stderr_bytes, max_stderr=max_stderr,
            args_digest=args_digest,
        )

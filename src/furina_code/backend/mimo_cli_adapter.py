"""Furina Code backend — MiMo Code CLI adapter.

Implements the BackendPort protocol using the MiMo CLI (`mimo run`).
Does NOT create CandidateEnvelope, write Ledger, or transition TaskRun.
Does NOT import ledger, formal objects factories, or orchestration modules.

Each invocation:
- creates a fresh temporary CWD outside the repository
- never passes --continue
- captures bounded stdout/stderr
- validates structured output, not just exit code
- cleans up temporary CWD
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

# Stable error messages (no paths, no credential values)
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


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MiMoCodeCLIAdapter:
    """BackendPort implementation using the MiMo CLI.

    Runtime parameters are injected via constructor (non-serialized).
    Each invoke creates a fresh temp CWD and never reuses sessions.
    """

    def __init__(
        self,
        *,
        mimo_executable: str = "mimo",
        default_model: str | None = None,
        forbidden_roots: tuple[Path, ...] = (),
    ) -> None:
        self._mimo_executable = mimo_executable
        self._default_model = default_model
        self._forbidden_roots = tuple(Path(r) for r in forbidden_roots)

    def probe(self, request: BackendProbeRequest) -> BackendProbeResult:
        """Check if MiMo executable is available."""
        errors: list[str] = []

        # Check executable exists
        try:
            result = subprocess.run(
                [self._mimo_executable, "--version"],
                capture_output=True, text=True, timeout=10,
                shell=False,
            )
            version = result.stdout.strip() if result.returncode == 0 else None
            if result.returncode != 0:
                errors.append("executable_not_found")
        except FileNotFoundError:
            errors.append("executable_not_found")
            version = None
        except subprocess.TimeoutExpired:
            errors.append("executable_not_found")
            version = None
        except OSError:
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
        """Verify request digest and generate invocation plan."""
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
        """Execute MiMo CLI in a fresh temp CWD and capture output."""
        request = plan.request

        # Create fresh temp CWD outside repository
        temp_cwd = Path(tempfile.mkdtemp(prefix="furina_mimo_"))

        # Ensure temp CWD is not inside any forbidden root
        temp_cwd_resolved = temp_cwd.resolve()
        for forbidden in self._forbidden_roots:
            try:
                temp_cwd_resolved.relative_to(forbidden.resolve())
                # Inside forbidden — clean up and fail
                shutil.rmtree(temp_cwd, ignore_errors=True)
                return self._error_result(
                    request, TransportStatus.SANDBOX_VIOLATION,
                    "sandbox_violation",
                )
            except ValueError:
                pass

        started_at = _now_iso()
        max_stdout = request.max_stdout_bytes
        max_stderr = request.max_stderr_bytes

        try:
            return self._run_process(
                plan, temp_cwd, started_at, max_stdout, max_stderr,
            )
        finally:
            # Always clean up temp CWD
            shutil.rmtree(temp_cwd, ignore_errors=True)

    def _run_process(
        self,
        plan: BackendInvocationPlan,
        temp_cwd: Path,
        started_at: str,
        max_stdout: int,
        max_stderr: int,
    ) -> BackendTransportResult:
        """Run the MiMo process and handle all error paths."""
        request = plan.request
        args = list(plan.executable_args)

        timeout = max(request.timeout_seconds, 1) if request.timeout_seconds > 0 else 300

        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(temp_cwd),
                shell=False,
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    if sys.platform == "win32" else 0
                ),
            )
        except FileNotFoundError:
            return self._error_result(
                request, TransportStatus.LAUNCH_FAILED,
                "executable_not_found",
            )
        except OSError as exc:
            return self._error_result(
                request, TransportStatus.LAUNCH_FAILED,
                "launch_failed",
            )

        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Kill process tree
            self._kill_process_tree(proc)
            stdout_bytes = proc.stdout.read() if proc.stdout else b""
            stderr_bytes = proc.stderr.read() if proc.stderr else b""
            proc.wait()
            finished_at = _now_iso()

            stdout_truncated, stdout_digest, stdout_ref = self._capture_stream(
                stdout_bytes, max_stdout,
            )
            stderr_truncated, stderr_digest, stderr_ref = self._capture_stream(
                stderr_bytes, max_stderr,
            )

            return self._make_result(
                request,
                transport_status=TransportStatus.TIMEOUT.value,
                error_code="timeout_expired",
                error_detail=_ERROR_MESSAGES["timeout_expired"],
                started_at=started_at,
                finished_at=finished_at,
                stdout_ref=stdout_ref,
                stdout_digest=stdout_digest,
                stdout_bytes=len(stdout_bytes),
                stdout_truncated=stdout_truncated,
                stderr_ref=stderr_ref,
                stderr_digest=stderr_digest,
                stderr_bytes=len(stderr_bytes),
                stderr_truncated=stderr_truncated,
            )

        finished_at = _now_iso()
        exit_code = proc.returncode

        # Capture streams with limits
        stdout_truncated, stdout_digest, stdout_ref = self._capture_stream(
            stdout_bytes, max_stdout,
        )
        stderr_truncated, stderr_digest, stderr_ref = self._capture_stream(
            stderr_bytes, max_stderr,
        )

        # Check exit code
        if exit_code != 0:
            # Even with non-zero exit, check stderr for model errors
            stderr_text = self._safe_decode(stderr_bytes)
            error_code, error_detail = self._classify_stderr(stderr_text)
            return self._make_result(
                request,
                transport_status=TransportStatus.NONZERO_EXIT.value,
                error_code=error_code,
                error_detail=error_detail,
                started_at=started_at,
                finished_at=finished_at,
                stdout_ref=stdout_ref,
                stdout_digest=stdout_digest,
                stdout_bytes=len(stdout_bytes),
                stdout_truncated=stdout_truncated,
                stderr_ref=stderr_ref,
                stderr_digest=stderr_digest,
                stderr_bytes=len(stderr_bytes),
                stderr_truncated=stderr_truncated,
            )

        # Exit code 0 — parse stdout JSON
        stdout_text = self._safe_decode(stdout_bytes)
        if stdout_text is None:
            return self._make_result(
                request,
                transport_status=TransportStatus.INVALID_UTF8.value,
                error_code="invalid_utf8",
                error_detail=_ERROR_MESSAGES["invalid_utf8"],
                started_at=started_at,
                finished_at=finished_at,
                stdout_ref=stdout_ref,
                stdout_digest=stdout_digest,
                stdout_bytes=len(stdout_bytes),
                stdout_truncated=stdout_truncated,
                stderr_ref=stderr_ref,
                stderr_digest=stderr_digest,
                stderr_bytes=len(stderr_bytes),
                stderr_truncated=stderr_truncated,
            )

        # Validate JSON
        parsed_lines = self._parse_jsonl(stdout_text)
        if parsed_lines is None:
            return self._make_result(
                request,
                transport_status=TransportStatus.PROTOCOL_ERROR.value,
                error_code="protocol_error",
                error_detail=_ERROR_MESSAGES["protocol_error"],
                started_at=started_at,
                finished_at=finished_at,
                stdout_ref=stdout_ref,
                stdout_digest=stdout_digest,
                stdout_bytes=len(stdout_bytes),
                stdout_truncated=stdout_truncated,
                stderr_ref=stderr_ref,
                stderr_digest=stderr_digest,
                stderr_bytes=len(stderr_bytes),
                stderr_truncated=stderr_truncated,
            )

        # Check for provider/model errors even with exit code 0
        stderr_text = self._safe_decode(stderr_bytes) or ""
        if self._has_provider_error(stderr_text, parsed_lines):
            error_code, error_detail = self._classify_stderr(stderr_text)
            return self._make_result(
                request,
                transport_status=TransportStatus.PROTOCOL_ERROR.value,
                error_code=error_code,
                error_detail=error_detail,
                started_at=started_at,
                finished_at=finished_at,
                stdout_ref=stdout_ref,
                stdout_digest=stdout_digest,
                stdout_bytes=len(stdout_bytes),
                stdout_truncated=stdout_truncated,
                stderr_ref=stderr_ref,
                stderr_digest=stderr_digest,
                stderr_bytes=len(stderr_bytes),
                stderr_truncated=stderr_truncated,
            )

        # Extract text content from JSONL events
        text_content = self._extract_text(parsed_lines)
        if not text_content:
            return self._make_result(
                request,
                transport_status=TransportStatus.PROTOCOL_ERROR.value,
                error_code="protocol_error",
                error_detail="MiMo produced no text output.",
                started_at=started_at,
                finished_at=finished_at,
                stdout_ref=stdout_ref,
                stdout_digest=stdout_digest,
                stdout_bytes=len(stdout_bytes),
                stdout_truncated=stdout_truncated,
                stderr_ref=stderr_ref,
                stderr_digest=stderr_digest,
                stderr_bytes=len(stderr_bytes),
                stderr_truncated=stderr_truncated,
            )

        # Extract session ID from events
        session_id = None
        for line in parsed_lines:
            if isinstance(line, dict) and "sessionID" in line:
                session_id = line["sessionID"]
                break

        # Build candidate content
        candidate = self._build_candidate(request, text_content)

        # Write candidate to sandbox
        candidate_bytes = _json.dumps(candidate, ensure_ascii=False).encode("utf-8")

        # Check size limit
        effective_limit = min(max_stdout, 10 * 1024 * 1024)
        if len(candidate_bytes) > effective_limit:
            return self._make_result(
                request,
                transport_status=TransportStatus.OUTPUT_TOO_LARGE.value,
                error_code="output_too_large",
                error_detail=_ERROR_MESSAGES["output_too_large"],
                started_at=started_at,
                finished_at=finished_at,
                stdout_ref=stdout_ref,
                stdout_digest=stdout_digest,
                stdout_bytes=len(stdout_bytes),
                stdout_truncated=stdout_truncated,
                stderr_ref=stderr_ref,
                stderr_digest=stderr_digest,
                stderr_bytes=len(stderr_bytes),
                stderr_truncated=stderr_truncated,
            )

        return self._make_result(
            request,
            transport_status=TransportStatus.SUCCEEDED.value,
            error_code=None,
            error_detail=None,
            started_at=started_at,
            finished_at=finished_at,
            stdout_ref=stdout_ref,
            stdout_digest=stdout_digest,
            stdout_bytes=len(stdout_bytes),
            stdout_truncated=stdout_truncated,
            stderr_ref=stderr_ref,
            stderr_digest=stderr_digest,
            stderr_bytes=len(stderr_bytes),
            stderr_truncated=stderr_truncated,
            candidate_ref=f"{request.sandbox_path_ref}/candidate.json",
            candidate_digest=_sha256_bytes(candidate_bytes),
            provider_session_ref=session_id,
        )

    def collect(
        self,
        plan: BackendInvocationPlan,
        transport: BackendTransportResult,
    ) -> BackendTransportResult:
        """Collect is a no-op for CLI adapter — candidate written by invoke."""
        return transport

    def strict_validate(
        self,
        request: BackendInvocationRequest,
        transport: BackendTransportResult,
    ) -> BackendTransportResult:
        """Validate transport result bindings."""
        if transport.transport_status != TransportStatus.SUCCEEDED.value:
            return transport

        if not transport.candidate_ref:
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.AMBIGUOUS.value,
                error_code="candidate_evidence_mismatch",
                error_detail="No candidate reference in transport result.",
                finished_at=_now_iso(),
            )

        if not transport.candidate_digest:
            return dataclasses.replace(
                transport,
                transport_status=TransportStatus.AMBIGUOUS.value,
                error_code="candidate_evidence_mismatch",
                error_detail="No candidate digest in transport result.",
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

        return transport

    # --- Internal helpers ---

    @staticmethod
    def _kill_process_tree(proc: subprocess.Popen) -> None:
        """Kill process and all children."""
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
        """Decode bytes to string, returning None on failure."""
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    @staticmethod
    def _parse_jsonl(text: str) -> list[dict] | None:
        """Parse newline-delimited JSON. Returns None on parse failure."""
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
        """Extract text content from JSONL events."""
        for event in events:
            if event.get("type") == "text":
                part = event.get("part", {})
                text = part.get("text")
                if text:
                    return text
        return None

    @staticmethod
    def _has_provider_error(stderr_text: str, events: list[dict]) -> bool:
        """Check for provider/model errors in stderr or events."""
        error_indicators = [
            "Error:", "error:", "ProviderModelNotFoundError",
            "not found", "failed", "authentication",
        ]
        for indicator in error_indicators:
            if indicator in stderr_text:
                return True
        return False

    @staticmethod
    def _classify_stderr(stderr_text: str) -> tuple[str, str]:
        """Classify stderr into stable error code and detail."""
        lower = stderr_text.lower()
        if "model not found" in lower or "providernotfounderror" in lower:
            return "provider_error", "MiMo reported model not found."
        if "authentication" in lower or "unauthorized" in lower:
            return "provider_error", "MiMo reported authentication failure."
        if "timeout" in lower:
            return "timeout_expired", _ERROR_MESSAGES["timeout_expired"]
        return "nonzero_exit", _ERROR_MESSAGES["nonzero_exit"]

    def _capture_stream(
        self, data: bytes, max_bytes: int,
    ) -> tuple[bool, str, str | None]:
        """Capture a stream with limit. Returns (truncated, digest, ref)."""
        truncated = len(data) > max_bytes
        digest = _sha256_bytes(data[:max_bytes])
        return truncated, digest, None  # ref is None — not written to disk

    def _build_candidate(
        self, request: BackendInvocationRequest, text_content: str,
    ) -> dict:
        """Build candidate JSON structure."""
        return {
            "schema_version": "1.0",
            "candidate_type": "mimo_cli_response",
            "backend_profile_ref": request.backend_profile_ref,
            "backend_session_ref": request.backend_session_ref,
            "context_ref": request.context_ref,
            "context_digest": request.context_digest,
            "content": {
                "text": text_content,
                "model_ref": request.model_ref,
                "instruction_text_hash": hashlib.sha256(
                    request.instruction_text.encode("utf-8")
                ).hexdigest(),
            },
            "claimed_assumptions": [],
            "requested_actions": [],
        }

    def _make_result(
        self,
        request: BackendInvocationRequest,
        *,
        transport_status: str,
        error_code: str | None,
        error_detail: str | None,
        started_at: str,
        finished_at: str,
        stdout_ref: str | None = None,
        stdout_digest: str | None = None,
        stdout_bytes: int = 0,
        stdout_truncated: bool = False,
        stderr_ref: str | None = None,
        stderr_digest: str | None = None,
        stderr_bytes: int = 0,
        stderr_truncated: bool = False,
        candidate_ref: str | None = None,
        candidate_digest: str | None = None,
        provider_session_ref: str | None = None,
    ) -> BackendTransportResult:
        return BackendTransportResult(
            invocation_id=request.invocation_id,
            request_digest=request.request_digest,
            backend_session_ref=request.backend_session_ref,
            provider_session_ref=provider_session_ref,
            provider_ref="mimo-cli",
            executable_version="mimo-cli-1.0",
            started_at=started_at,
            finished_at=finished_at,
            command_args_digest=compute_empty_args_digest(),
            stdout_ref=stdout_ref,
            stdout_digest=stdout_digest,
            stdout_bytes=stdout_bytes,
            stdout_truncated=stdout_truncated,
            stderr_ref=stderr_ref,
            stderr_digest=stderr_digest,
            stderr_bytes=stderr_bytes,
            stderr_truncated=stderr_truncated,
            candidate_ref=candidate_ref,
            candidate_digest=candidate_digest,
            manifest_before_ref=None,
            manifest_before_digest=None,
            manifest_after_ref=None,
            manifest_after_digest=None,
            transport_status=transport_status,
            error_code=error_code,
            error_detail=error_detail,
        )

    def _error_result(
        self,
        request: BackendInvocationRequest,
        status: TransportStatus,
        error_code: str,
    ) -> BackendTransportResult:
        return BackendTransportResult(
            invocation_id=request.invocation_id,
            request_digest=request.request_digest,
            backend_session_ref=request.backend_session_ref,
            provider_session_ref=None,
            provider_ref="mimo-cli",
            executable_version="mimo-cli-1.0",
            started_at=_now_iso(),
            finished_at=_now_iso(),
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

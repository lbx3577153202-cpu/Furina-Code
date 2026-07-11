"""E3 tests — runtime/git boundary."""

import subprocess
import sys
from pathlib import Path


class TestRuntimeGitBoundary:
    def test_runtime_directory_ignored_by_git(self, tmp_path):
        """Verify that .sqlite3 files are ignored by git."""
        # Create a dummy sqlite file in the repo's runtime directory
        repo_root = Path(__file__).resolve().parents[2]
        runtime_dir = repo_root / "runtime"
        runtime_dir.mkdir(exist_ok=True)
        test_file = runtime_dir / "e3-test.sqlite3"
        test_file.write_text("dummy")

        try:
            result = subprocess.run(
                ["git", "check-ignore", str(test_file)],
                capture_output=True, text=True, shell=False,
                cwd=str(repo_root),
            )
            # git check-ignore returns 0 if file is ignored
            assert result.returncode == 0, f"runtime/*.sqlite3 not ignored by git: {result.stdout} {result.stderr}"
            assert str(test_file) in result.stdout or "runtime" in result.stdout
        finally:
            test_file.unlink(missing_ok=True)

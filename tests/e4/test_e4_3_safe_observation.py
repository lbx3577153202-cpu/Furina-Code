"""E4.3 tests — structured safe file observation."""

import subprocess
from pathlib import Path
from furina_code.world.observe import safe_observe_file, observe_project, SafeFileObservation


class TestSafeFileObservation:
    def test_present_file(self):
        """Normal file returns present status with content and sha256."""
        repo = Path(__file__).resolve().parents[2]
        obs = safe_observe_file(repo / "pyproject.toml", repo)
        assert obs.status == "present"
        assert obs.content is not None
        assert obs.sha256.startswith("sha256:")
        assert obs.size_bytes is not None
        assert obs.size_bytes > 0

    def test_missing_file(self):
        """Missing file returns missing status."""
        repo = Path(__file__).resolve().parents[2]
        obs = safe_observe_file(repo / "nonexistent_file.toml", repo)
        assert obs.status == "missing"
        assert obs.content is None
        assert obs.reason is not None

    def test_symlink_rejected(self, tmp_path):
        """Symlink file returns symlink_rejected."""
        repo = tmp_path / "repo"
        repo.mkdir()
        real = repo / "real.txt"
        real.write_text("hello")
        link = repo / "link.txt"
        link.symlink_to(real)

        obs = safe_observe_file(link, repo)
        assert obs.status == "symlink_rejected"
        assert obs.content is None

    def test_escape_rejected(self, tmp_path):
        """File outside repo root returns escape_rejected."""
        repo = tmp_path / "repo"
        repo.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("secret")

        obs = safe_observe_file(outside, repo)
        assert obs.status == "escape_rejected"
        assert obs.content is None

    def test_git_internal_rejected(self, tmp_path):
        """File inside .git returns git_internal_rejected."""
        repo = tmp_path / "repo"
        repo.mkdir()
        git_dir = repo / ".git"
        git_dir.mkdir()
        git_file = git_dir / "config"
        git_file.write_text("[core]")

        obs = safe_observe_file(git_file, repo)
        assert obs.status == "git_internal_rejected"
        assert obs.content is None

    def test_oversized_file(self, tmp_path):
        """File exceeding max_bytes returns oversized with sha256."""
        repo = tmp_path / "repo"
        repo.mkdir()
        big = repo / "big.txt"
        big.write_bytes(b"x" * 2_000_000)

        obs = safe_observe_file(big, repo, max_bytes=1_000_000)
        assert obs.status == "oversized"
        assert obs.content is None
        assert obs.sha256.startswith("sha256:")
        assert obs.size_bytes == 2_000_000

    def test_parent_symlink_escape_rejected(self, tmp_path):
        """Parent directory symlink escape must be rejected."""
        repo = tmp_path / "repo"
        repo.mkdir()
        outside = tmp_path / "outside_dir"
        outside.mkdir()
        target = outside / "file.txt"
        target.write_text("escaped")

        # Create a symlink inside repo that points outside
        link_dir = repo / "link_dir"
        link_dir.symlink_to(outside)

        obs = safe_observe_file(link_dir / "file.txt", repo)
        assert obs.status in ("escape_rejected", "symlink_rejected")


class TestObserveProjectStructured:
    def test_normal_missing_distinguished_from_rejected(self, tmp_path):
        """Normal missing and security rejection produce different blind spots."""
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, shell=False)
        subprocess.run(["git", "config", "user.email", "test@test.com"],
                       cwd=str(repo), capture_output=True, shell=False)
        subprocess.run(["git", "config", "user.name", "Test"],
                       cwd=str(repo), capture_output=True, shell=False)
        (repo / "test.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, shell=False)
        subprocess.run(["git", "commit", "-m", "init"],
                       cwd=str(repo), capture_output=True, shell=False)

        result = observe_project(str(repo), repository_root=str(repo))
        # No pyproject.toml — normal missing
        assert result["pyproject_exists"] is False
        # blind_spots should mention missing, not rejected
        assert any("missing" in bs for bs in result["blind_spots"])

    def test_symlink_pyproject_rejected(self, tmp_path):
        """Symlink pyproject.toml must be rejected."""
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, shell=False)
        subprocess.run(["git", "config", "user.email", "test@test.com"],
                       cwd=str(repo), capture_output=True, shell=False)
        subprocess.run(["git", "config", "user.name", "Test"],
                       cwd=str(repo), capture_output=True, shell=False)

        # Create a real pyproject.toml outside repo
        outside = tmp_path / "outside"
        outside.mkdir()
        real_pyproject = outside / "pyproject.toml"
        real_pyproject.write_text('[project]\nname = "test"')

        # Symlink it into repo
        link = repo / "pyproject.toml"
        link.symlink_to(real_pyproject)

        (repo / "test.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, shell=False)
        subprocess.run(["git", "commit", "-m", "init"],
                       cwd=str(repo), capture_output=True, shell=False)

        result = observe_project(str(repo), repository_root=str(repo))
        assert result["pyproject_exists"] is False
        # Must record as rejected, not just missing
        assert any("symlink" in bs.lower() or "rejected" in bs.lower() for bs in result["blind_spots"])

    def test_blind_spots_accurate_for_clean_repo(self):
        """Clean repo with valid pyproject should have minimal blind spots."""
        repo = str(Path(__file__).resolve().parents[2])
        result = observe_project(repo, repository_root=repo)
        assert result["pyproject_exists"] is True
        # CI config exists in this repo
        assert result["ci_config_exists"] is True

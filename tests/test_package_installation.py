"""Package installation tests.

Verify that the furina_code package can be imported from the installed src layout.
These tests ensure the package is properly installed, not just importable via sys.path hacks.
"""

import subprocess
import sys
from pathlib import Path


def test_furina_code_importable():
    import furina_code
    assert furina_code.__version__ == "0.0.0"


def test_furina_code_src_layout_path():
    """Verify the module comes from the expected src/furina_code/ layout."""
    import furina_code
    mod_path = Path(furina_code.__file__).resolve()
    assert mod_path.exists(), f"Module file does not exist: {mod_path}"
    # Walk up to find the src directory
    parts = mod_path.parts
    assert "src" in parts, f"Module path does not contain 'src' directory: {mod_path}"
    src_idx = parts.index("src")
    assert parts[src_idx + 1] == "furina_code", f"'src' is not followed by 'furina_code': {mod_path}"


def test_furina_code_import_from_outside_repo(tmp_path):
    """Verify import works from outside the repo without sys.path manipulation."""
    result = subprocess.run(
        [sys.executable, "-c", "import furina_code; print(furina_code.__file__)"],
        capture_output=True,
        text=True,
        shell=False,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0, f"Import failed from outside repo: {result.stderr}"
    assert "furina_code" in result.stdout
    module_path = result.stdout.strip()
    assert module_path, "Module path is empty"
    # Verify it's not a local path hack (should point to installed package)
    assert "src" in module_path or "site-packages" in module_path, (
        f"Module path does not look like an installed package: {module_path}"
    )
    # Verify it's not the temp directory
    assert str(tmp_path) not in module_path, (
        f"Module was found in temp directory, not installed package: {module_path}"
    )

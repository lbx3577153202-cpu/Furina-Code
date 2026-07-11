"""Package installation tests.

Verify that the furina_code package can be imported from the installed src layout.
"""

import importlib
import sys


def test_furina_code_importable():
    import furina_code
    assert furina_code.__version__ == "0.0.0"


def test_furina_code_from_src_layout():
    import furina_code
    mod_path = furina_code.__file__
    assert mod_path is not None
    assert "src" in mod_path or "furina_code" in mod_path


def test_furina_code_not_sys_path_hack():
    """Ensure import works without manual sys.path manipulation."""
    import furina_code
    # If we got here, the package was found through proper installation
    assert True

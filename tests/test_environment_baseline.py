"""Environment baseline tests.

Verify that the minimum required resources are available for Furina Code.
These tests prove resource availability, not project functionality.
"""

import importlib
import sqlite3
import subprocess
import sys


def test_python_version_at_least_3_12():
    assert sys.version_info >= (3, 12), f"Python {sys.version} is below 3.12"


def test_stdlib_sqlite3_importable():
    import sqlite3
    assert hasattr(sqlite3, "connect")


def test_stdlib_subprocess_importable():
    import subprocess
    assert hasattr(subprocess, "run")


def test_stdlib_pathlib_importable():
    import pathlib
    assert hasattr(pathlib, "Path")


def test_stdlib_hashlib_importable():
    import hashlib
    assert hasattr(hashlib, "sha256")


def test_stdlib_json_importable():
    import json
    assert hasattr(json, "loads")


def test_stdlib_tomllib_importable():
    import tomllib
    assert hasattr(tomllib, "loads")


def test_sqlite_in_memory_create_write_read():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE test_kv (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    cur.execute("INSERT INTO test_kv (key, value) VALUES (?, ?)", ("hello", "world"))
    conn.commit()
    cur.execute("SELECT value FROM test_kv WHERE key = ?", ("hello",))
    row = cur.fetchone()
    conn.close()
    assert row == ("world",)


def test_sqlite_in_memory_transaction_rollback():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE test_tx (id INTEGER PRIMARY KEY, val TEXT)")
    conn.commit()
    cur.execute("BEGIN")
    cur.execute("INSERT INTO test_tx (id, val) VALUES (?, ?)", (1, "rolled_back"))
    conn.rollback()
    cur.execute("SELECT COUNT(*) FROM test_tx")
    count = cur.fetchone()[0]
    conn.close()
    assert count == 0


def test_git_cli_available():
    result = subprocess.run(
        ["git", "--version"],
        capture_output=True,
        text=True,
        shell=False,
    )
    assert result.returncode == 0, f"git --version failed: {result.stderr}"
    assert "git version" in result.stdout.lower()

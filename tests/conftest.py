"""
Shared pytest fixtures for AgentTrace production test suite.

Provides:
- fresh_db: Isolated SQLite database per test
- groq_client: Shared Groq client (skips if no API key)
- trace_steps: Helper fixture that queries and validates trace steps
"""

import os
import sqlite3

import pytest

# Disable agenttrace auto-server for all tests persistently
os.environ["AGENTTRACE_NO_SERVER"] = "1"

# Load .env from project root before any test (optional — CI won't have dotenv)
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Create a fresh, isolated SQLite DB for each test."""
    import agenttrace.storage as storage

    db_path = str(tmp_path / "test_agenttrace.db")
    monkeypatch.setenv("AGENTTRACE_DB_PATH", db_path)

    # Reset the module-level state so it picks up the new path
    storage.DB_PATH = db_path
    if hasattr(storage._local, "connection"):
        try:
            storage._local.connection.close()
        except Exception:
            pass
        del storage._local.connection

    storage._trace_id_var = storage.contextvars.ContextVar("trace_id", default=None)
    storage.init_db()

    yield db_path

    # Cleanup: close the connection
    if hasattr(storage._local, "connection"):
        try:
            storage._local.connection.close()
        except Exception:
            pass
        del storage._local.connection


@pytest.fixture
def groq_client():
    """Return a Groq client using the GROQ_API_KEY from .env, skip if not available."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key or api_key == "your_groq_api_key_here":
        pytest.skip("GROQ_API_KEY not set — skipping integration test")

    try:
        import groq
    except ImportError:
        pytest.skip("groq package not installed — run: pip install groq")

    return groq.Groq(api_key=api_key)


@pytest.fixture
def async_groq_client():
    """Return an async Groq client."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key or api_key == "your_groq_api_key_here":
        pytest.skip("GROQ_API_KEY not set — skipping integration test")

    try:
        import groq
    except ImportError:
        pytest.skip("groq package not installed — run: pip install groq")

    return groq.AsyncGroq(api_key=api_key)


def get_trace_steps(db_path, min_steps=1, expected_types=None):
    """
    Query the test DB and validate trace contents.

    Args:
        db_path: The path to the test database.
        min_steps: Minimum number of steps expected in the trace.
        expected_types: Optional list of step types that must appear.

    Returns:
        List of step rows for further assertions.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    steps = conn.execute("SELECT * FROM steps ORDER BY timestamp ASC").fetchall()
    conn.close()

    assert len(steps) >= min_steps, (
        f"Expected at least {min_steps} steps, got {len(steps)}"
    )

    if expected_types:
        found_types = {row["type"] for row in steps}
        for t in expected_types:
            assert t in found_types, (
                f"Expected step type '{t}' not found. Found: {found_types}"
            )

    return steps

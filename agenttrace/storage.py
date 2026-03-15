import contextvars
import json
import os
import sqlite3
import threading
from datetime import datetime

from .models import (
    AgentTrace,
    Dataset,
    DatasetItem,
    StepEvaluation,
    StepMetrics,
    TraceStep,
)
from .utils import truncate_payload

DB_PATH = os.environ.get("AGENTTRACE_DB_PATH", ".agenttrace.db")

_db_lock = threading.Lock()
_local = threading.local()


def _get_connection():
    if not hasattr(_local, "connection"):
        _local.connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.connection.execute("PRAGMA journal_mode=WAL")
        _local.connection.execute("PRAGMA busy_timeout=5000")
        _local.connection.row_factory = sqlite3.Row
    return _local.connection


def init_db():
    with _db_lock:
        conn = _get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY,
                session_id TEXT,
                tags TEXT,
                timestamp TEXT,
                status TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS steps (
                step_id TEXT PRIMARY KEY,
                parent_id TEXT,
                trace_id TEXT,
                type TEXT,
                name TEXT,
                inputs TEXT,
                outputs TEXT,
                metrics TEXT,
                evaluation TEXT,
                timestamp TEXT,
                FOREIGN KEY(trace_id) REFERENCES traces(trace_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dataset_items (
                item_id TEXT PRIMARY KEY,
                dataset_id TEXT,
                inputs TEXT,
                expected_outputs TEXT,
                created_at TEXT,
                FOREIGN KEY(dataset_id) REFERENCES datasets(dataset_id)
            )
        """)
        # Auto-migrations for existing databases
        for col, table in [("parent_id", "steps"), ("session_id", "traces"), ("tags", "traces")]:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()


init_db()


def _parse_tags_env():
    """Parse AGENTTRACE_TAGS env var (comma-separated key=value pairs) into a dict."""
    raw = os.environ.get("AGENTTRACE_TAGS", "")
    if not raw:
        return None
    tags = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            tags[k.strip()] = v.strip()
    return tags if tags else None
# Use ContextVar instead of a global variable for thread-safe multi-agent isolation
_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)


def set_current_trace_id(trace_id: str):
    _trace_id_var.set(trace_id)


def get_current_trace() -> AgentTrace:
    trace_id = _trace_id_var.get()

    with _db_lock:
        conn = _get_connection()

        if trace_id is None:
            # Create a new trace
            new_trace = AgentTrace(
                session_id=os.environ.get("AGENTTRACE_SESSION_ID"),
                tags=_parse_tags_env(),
            )
            _trace_id_var.set(new_trace.trace_id)
            conn.execute(
                "INSERT INTO traces (trace_id, session_id, tags, timestamp, status) VALUES (?, ?, ?, ?, ?)",
                (new_trace.trace_id, new_trace.session_id, json.dumps(new_trace.tags) if new_trace.tags else None, new_trace.timestamp.isoformat(), new_trace.status),
            )
            conn.commit()
            return new_trace

        # Load the existing trace
        row = conn.execute(
            "SELECT * FROM traces WHERE trace_id = ?", (trace_id,)
        ).fetchone()
        if not row:
            new_trace = AgentTrace(
                session_id=os.environ.get("AGENTTRACE_SESSION_ID"),
                tags=_parse_tags_env(),
            )
            new_trace.trace_id = trace_id
            conn.execute(
                "INSERT INTO traces (trace_id, session_id, tags, timestamp, status) VALUES (?, ?, ?, ?, ?)",
                (new_trace.trace_id, new_trace.session_id, json.dumps(new_trace.tags) if new_trace.tags else None, new_trace.timestamp.isoformat(), new_trace.status),
            )
            conn.commit()
            return new_trace

        trace = AgentTrace(
            trace_id=row["trace_id"],
            session_id=row["session_id"] if "session_id" in row.keys() else None,
            tags=json.loads(row["tags"]) if ("tags" in row.keys() and row["tags"]) else None,
            timestamp=datetime.fromisoformat(row["timestamp"]),
            status=row["status"],
            steps=[],
        )

        # Load steps
        steps_rows = conn.execute(
            "SELECT * FROM steps WHERE trace_id = ? ORDER BY timestamp ASC", (trace_id,)
        ).fetchall()
        for s_row in steps_rows:
            step = TraceStep(
                step_id=s_row["step_id"],
                parent_id=s_row["parent_id"] if "parent_id" in s_row.keys() else None,
                type=s_row["type"],
                name=s_row["name"],
                inputs=json.loads(s_row["inputs"]),
                outputs=json.loads(s_row["outputs"]),
                metrics=StepMetrics.model_validate_json(s_row["metrics"]),
                evaluation=StepEvaluation.model_validate_json(s_row["evaluation"]),
                timestamp=datetime.fromisoformat(s_row["timestamp"]),
            )
            trace.steps.append(step)

        return trace


def clear_trace():
    trace_id = _trace_id_var.get()
    if trace_id:
        update_trace_status(trace_id, "completed")
    _trace_id_var.set(None)


def update_trace_status(trace_id: str, status: str):
    """Mark a trace as running, completed, or error."""
    with _db_lock:
        conn = _get_connection()
        conn.execute(
            "UPDATE traces SET status = ? WHERE trace_id = ?", (status, trace_id)
        )
        conn.commit()


def prune_traces():
    """Keep only the latest AGENTTRACE_MAX_TRACES in the database."""
    max_traces = int(os.environ.get("AGENTTRACE_MAX_TRACES", "100"))
    if max_traces <= 0:
        return

    with _db_lock:
        conn = _get_connection()
        conn.execute(
            """
            DELETE FROM traces WHERE trace_id NOT IN (
                SELECT trace_id FROM traces ORDER BY timestamp DESC LIMIT ?
            )
            """,
            (max_traces,),
        )
        conn.execute(
            """
            DELETE FROM steps WHERE trace_id NOT IN (
                SELECT trace_id FROM traces
            )
            """
        )
        conn.commit()


def clear_all_traces():
    """Manually delete all traces and steps from the database."""
    with _db_lock:
        conn = _get_connection()
        conn.execute("DELETE FROM steps")
        conn.execute("DELETE FROM traces")
        conn.commit()


def add_step(step: TraceStep):
    """Append a step to the current trace."""
    trace = get_current_trace()

    # Pre-truncate inputs and outputs for DB storage
    safe_inputs = json.dumps(truncate_payload(step.inputs))
    safe_outputs = json.dumps(truncate_payload(step.outputs))

    with _db_lock:
        conn = _get_connection()
        conn.execute(
            """
            INSERT INTO steps (step_id, parent_id, trace_id, type, name, inputs, outputs, metrics, evaluation, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                step.step_id,
                step.parent_id,
                trace.trace_id,
                step.type,
                step.name,
                safe_inputs,
                safe_outputs,
                step.metrics.model_dump_json(),
                step.evaluation.model_dump_json(),
                step.timestamp.isoformat(),
            ),
        )
        conn.commit()


def update_step(step: TraceStep):
    """Update an existing step in the current trace (useful for evaluations)."""
    safe_outputs = json.dumps(truncate_payload(step.outputs))

    with _db_lock:
        conn = _get_connection()
        conn.execute(
            """
            UPDATE steps SET
                outputs = ?,
                metrics = ?,
                evaluation = ?,
                timestamp = ?
            WHERE step_id = ?
        """,
            (
                safe_outputs,
                step.metrics.model_dump_json(),
                step.evaluation.model_dump_json(),
                step.timestamp.isoformat(),
                step.step_id,
            ),
        )
        conn.commit()


def list_traces(limit: int = 50):
    with _db_lock:
        conn = _get_connection()
        rows = conn.execute(
            "SELECT * FROM traces ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()

        traces = []
        for row in rows:
            traces.append(
                AgentTrace(
                    trace_id=row["trace_id"],
                    session_id=row["session_id"] if "session_id" in row.keys() else None,
                    tags=json.loads(row["tags"]) if ("tags" in row.keys() and row["tags"]) else None,
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    status=row["status"],
                    steps=[],  # Steps not loaded for list view
                )
            )
        return traces


def list_sessions(limit: int = 50):
    with _db_lock:
        conn = _get_connection()
        rows = conn.execute(
            """
            SELECT session_id, count(trace_id) as trace_count, max(timestamp) as latest_timestamp
            FROM traces
            WHERE session_id IS NOT NULL
            GROUP BY session_id
            ORDER BY latest_timestamp DESC LIMIT ?
            """, (limit,)
        ).fetchall()

        sessions = []
        for row in rows:
            sessions.append({
                "session_id": row["session_id"],
                "trace_count": row["trace_count"],
                "latest_timestamp": row["latest_timestamp"],
            })
        return sessions


def get_session_traces(session_id: str):
    with _db_lock:
        conn = _get_connection()
        rows = conn.execute(
            "SELECT * FROM traces WHERE session_id = ? ORDER BY timestamp DESC", (session_id,)
        ).fetchall()

        traces = []
        for row in rows:
            traces.append(
                AgentTrace(
                    trace_id=row["trace_id"],
                    session_id=row["session_id"] if "session_id" in row.keys() else None,
                    tags=json.loads(row["tags"]) if ("tags" in row.keys() and row["tags"]) else None,
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    status=row["status"],
                    steps=[],  # Steps not loaded for full session view by default to save memory
                )
            )
        return traces



def get_trace_by_id(trace_id: str):
    with _db_lock:
        conn = _get_connection()
        row = conn.execute(
            "SELECT * FROM traces WHERE trace_id = ?", (trace_id,)
        ).fetchone()
        if not row:
            return None

        trace = AgentTrace(
            trace_id=row["trace_id"],
            session_id=row["session_id"] if "session_id" in row.keys() else None,
            tags=json.loads(row["tags"]) if ("tags" in row.keys() and row["tags"]) else None,
            timestamp=datetime.fromisoformat(row["timestamp"]),
            status=row["status"],
            steps=[],
        )

        steps_rows = conn.execute(
            "SELECT * FROM steps WHERE trace_id = ? ORDER BY timestamp ASC", (trace_id,)
        ).fetchall()
        for s_row in steps_rows:
            step = TraceStep(
                step_id=s_row["step_id"],
                parent_id=s_row["parent_id"] if "parent_id" in s_row.keys() else None,
                type=s_row["type"],
                name=s_row["name"],
                inputs=json.loads(s_row["inputs"]),
                outputs=json.loads(s_row["outputs"]),
                metrics=StepMetrics.model_validate_json(s_row["metrics"]),
                evaluation=StepEvaluation.model_validate_json(s_row["evaluation"]),
                timestamp=datetime.fromisoformat(s_row["timestamp"]),
            )
            trace.steps.append(step)

        return trace


def get_all_traces():
    # Only returns the current trace for MVP compatibility. Use list_traces instead.
    trace = get_current_trace()
    return [trace] if trace else []


def add_step_with_trace_id(step: TraceStep, trace_id: str, session_id: str | None = None, tags: dict | None = None):
    """Append a step to a specific trace by ID, bypassing ContextVars. Used by exporters."""
    safe_inputs = json.dumps(truncate_payload(step.inputs))
    safe_outputs = json.dumps(truncate_payload(step.outputs))

    with _db_lock:
        conn = _get_connection()

        # Ensure the trace exists
        row = conn.execute(
            "SELECT trace_id, session_id, tags FROM traces WHERE trace_id = ?", (trace_id,)
        ).fetchone()
        if not row:
            t = AgentTrace(
                trace_id=trace_id,
                session_id=session_id,
                tags=tags,
                timestamp=datetime.now(),
                status="running",
                steps=[],
            )
            conn.execute(
                "INSERT INTO traces (trace_id, session_id, tags, timestamp, status) VALUES (?, ?, ?, ?, ?)",
                (t.trace_id, t.session_id, json.dumps(t.tags) if t.tags else None, t.timestamp.isoformat(), t.status),
            )
        else:
            # Update session/tags if they were provided in this span but trace didn't have them
            current_session = row["session_id"] if "session_id" in row.keys() else None
            needs_update = False
            if session_id and not current_session:
                needs_update = True

            # Simple merge of tags for MVP
            current_tags = json.loads(row["tags"]) if ("tags" in row.keys() and row["tags"]) else {}
            if tags:
                for k, v in tags.items():
                    if k not in current_tags:
                        current_tags[k] = v
                        needs_update = True

            if needs_update:
                conn.execute(
                    "UPDATE traces SET session_id = COALESCE(session_id, ?), tags = ? WHERE trace_id = ?",
                    (session_id, json.dumps(current_tags) if current_tags else None, trace_id)
                )

        # Insert the step
        conn.execute(
            """
            INSERT INTO steps (step_id, parent_id, trace_id, type, name, inputs, outputs, metrics, evaluation, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                step.step_id,
                step.parent_id,
                trace_id,
                step.type,
                step.name,
                safe_inputs,
                safe_outputs,
                step.metrics.model_dump_json(),
                step.evaluation.model_dump_json(),
                step.timestamp.isoformat(),
            ),
        )
        conn.commit()


def create_dataset(name: str, description: str | None = None) -> Dataset:
    ds = Dataset(name=name, description=description)
    with _db_lock:
        conn = _get_connection()
        conn.execute(
            "INSERT INTO datasets (dataset_id, name, description, created_at) VALUES (?, ?, ?, ?)",
            (ds.dataset_id, ds.name, ds.description, ds.created_at.isoformat())
        )
        conn.commit()
    return ds

def list_datasets() -> list[Dataset]:
    with _db_lock:
        conn = _get_connection()
        rows = conn.execute("SELECT * FROM datasets ORDER BY created_at DESC").fetchall()

        datasets = []
        for row in rows:
            datasets.append(Dataset(
                dataset_id=row["dataset_id"],
                name=row["name"],
                description=row["description"],
                created_at=datetime.fromisoformat(row["created_at"])
            ))
        return datasets

def get_dataset(dataset_id: str) -> Dataset | None:
    with _db_lock:
        conn = _get_connection()
        row = conn.execute("SELECT * FROM datasets WHERE dataset_id = ?", (dataset_id,)).fetchone()
        if not row:
            return None
        return Dataset(
            dataset_id=row["dataset_id"],
            name=row["name"],
            description=row["description"],
            created_at=datetime.fromisoformat(row["created_at"])
        )

def add_dataset_item(dataset_id: str, inputs: dict, expected_outputs: dict | None = None) -> DatasetItem:
    item = DatasetItem(dataset_id=dataset_id, inputs=inputs, expected_outputs=expected_outputs)
    with _db_lock:
        conn = _get_connection()
        conn.execute(
            "INSERT INTO dataset_items (item_id, dataset_id, inputs, expected_outputs, created_at) VALUES (?, ?, ?, ?, ?)",
            (item.item_id, item.dataset_id, json.dumps(item.inputs), json.dumps(item.expected_outputs) if item.expected_outputs else None, item.created_at.isoformat())
        )
        conn.commit()
    return item

def list_dataset_items(dataset_id: str) -> list[DatasetItem]:
    with _db_lock:
        conn = _get_connection()
        rows = conn.execute("SELECT * FROM dataset_items WHERE dataset_id = ? ORDER BY created_at ASC", (dataset_id,)).fetchall()

        items = []
        for row in rows:
            items.append(DatasetItem(
                item_id=row["item_id"],
                dataset_id=row["dataset_id"],
                inputs=json.loads(row["inputs"]),
                expected_outputs=json.loads(row["expected_outputs"]) if row["expected_outputs"] else None,
                created_at=datetime.fromisoformat(row["created_at"])
            ))
        return items


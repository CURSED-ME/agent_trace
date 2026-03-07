import os
import json
import sqlite3
import threading
import contextvars
from datetime import datetime
from .models import AgentTrace, TraceStep, StepMetrics, StepEvaluation
from .utils import truncate_payload

DB_PATH = os.environ.get("AGENTTRACE_DB_PATH", ".agenttrace.db")

_db_lock = threading.Lock()
_connection = None


def _get_connection():
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA busy_timeout=5000")
        _connection.row_factory = sqlite3.Row
    return _connection


def init_db():
    with _db_lock:
        conn = _get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY,
                timestamp TEXT,
                status TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS steps (
                step_id TEXT PRIMARY KEY,
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
        conn.commit()


init_db()

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
            new_trace = AgentTrace()
            _trace_id_var.set(new_trace.trace_id)
            conn.execute(
                "INSERT INTO traces (trace_id, timestamp, status) VALUES (?, ?, ?)",
                (new_trace.trace_id, new_trace.timestamp.isoformat(), new_trace.status),
            )
            conn.commit()
            return new_trace

        # Load the existing trace
        row = conn.execute(
            "SELECT * FROM traces WHERE trace_id = ?", (trace_id,)
        ).fetchone()
        if not row:
            new_trace = AgentTrace()
            new_trace.trace_id = trace_id
            conn.execute(
                "INSERT INTO traces (trace_id, timestamp, status) VALUES (?, ?, ?)",
                (new_trace.trace_id, new_trace.timestamp.isoformat(), new_trace.status),
            )
            conn.commit()
            return new_trace

        trace = AgentTrace(
            trace_id=row["trace_id"],
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
    _trace_id_var.set(None)


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
            INSERT INTO steps (step_id, trace_id, type, name, inputs, outputs, metrics, evaluation, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                step.step_id,
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
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    status=row["status"],
                    steps=[],  # Steps not loaded for list view
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

"""
Test 3: Failure Modes
Validates crash handling, error propagation, and loop detection.
No API calls needed — all offline.
"""

import json
import sqlite3
import sys

import pytest


def _get_steps(db_path, min_steps=1, expected_types=None):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    steps = conn.execute("SELECT * FROM steps ORDER BY timestamp ASC").fetchall()
    conn.close()
    assert len(steps) >= min_steps, f"Expected >= {min_steps} steps, got {len(steps)}"
    if expected_types:
        found = {r["type"] for r in steps}
        for t in expected_types:
            assert t in found, f"Missing type '{t}'. Found: {found}"
    return steps


class TestCrashHandler:
    """Validate the sys.excepthook crash handler."""

    @pytest.mark.offline
    def test_crash_handler_records_step(self, fresh_db):
        from agenttrace.auto import crash_handler

        try:
            raise RuntimeError("Simulated agent crash: out of memory")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            crash_handler(exc_type, exc_value, exc_tb)

        steps = _get_steps(fresh_db, min_steps=1, expected_types=["server_crash"])
        step = steps[0]
        assert step["name"] == "Unhandled Exception"

        inputs = json.loads(step["inputs"])
        assert inputs["type"] == "RuntimeError"
        assert "out of memory" in inputs["value"]

        outputs = json.loads(step["outputs"])
        assert "traceback" in outputs
        assert "RuntimeError" in outputs["traceback"]

    @pytest.mark.offline
    def test_crash_handler_preserves_previous_steps(self, fresh_db):
        from agenttrace.auto import crash_handler
        from agenttrace.decorators import track_tool

        @track_tool
        def some_work():
            return "partial result"

        some_work()
        some_work()

        try:
            raise KeyError("missing_config_key")
        except KeyError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            crash_handler(exc_type, exc_value, exc_tb)

        steps = _get_steps(fresh_db, min_steps=3)
        types = [s["type"] for s in steps]
        assert types.count("tool_execution") == 2
        assert types.count("server_crash") == 1


class TestToolErrorPropagation:
    """Validate that tool errors are recorded but still propagate."""

    @pytest.mark.offline
    def test_tool_error_creates_step_with_error(self, fresh_db):
        from agenttrace.decorators import track_tool

        @track_tool
        def api_call(url):
            raise ConnectionError(f"Failed to connect to {url}")

        with pytest.raises(ConnectionError):
            api_call("https://broken.api.com")

        steps = _get_steps(fresh_db, min_steps=1)
        outputs = json.loads(steps[0]["outputs"])
        assert "error" in outputs
        assert "broken.api.com" in outputs["error"]

    @pytest.mark.offline
    def test_multiple_tool_errors_all_recorded(self, fresh_db):
        from agenttrace.decorators import track_tool

        @track_tool
        def flaky_tool(attempt):
            if attempt < 3:
                raise TimeoutError(f"Attempt {attempt} timed out")
            return "success"

        for i in range(1, 4):
            try:
                flaky_tool(i)
            except TimeoutError:
                pass

        steps = _get_steps(fresh_db, min_steps=3)
        out1 = json.loads(steps[0]["outputs"])
        out2 = json.loads(steps[1]["outputs"])
        out3 = json.loads(steps[2]["outputs"])
        assert "error" in out1
        assert "error" in out2
        assert out3["result"] == "success"


class TestLoopDetection:
    """Validate the judge's loop detection flags repeated identical tool calls."""

    @pytest.mark.offline
    def test_identical_calls_flagged(self, fresh_db):
        from agenttrace.judge import JudgeEngine
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, get_current_trace

        for i in range(5):
            add_step(
                TraceStep(
                    type="tool_execution",
                    name="search_api",
                    inputs={"query": "same query", "limit": 10},
                    outputs={"results": []},
                    metrics=StepMetrics(latency_ms=100),
                )
            )

        trace = get_current_trace()
        engine = JudgeEngine()
        pending = [s for s in trace.steps if s.evaluation.status == "pending"]
        engine._check_loops(trace, pending)

        flagged = [s for s in pending if "loop_detected" in s.evaluation.flags]
        assert len(flagged) >= 3, f"Expected 3+ flagged steps, got {len(flagged)}"

    @pytest.mark.offline
    def test_different_calls_not_flagged(self, fresh_db):
        from agenttrace.judge import JudgeEngine
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, get_current_trace

        for i in range(5):
            add_step(
                TraceStep(
                    type="tool_execution",
                    name="search_api",
                    inputs={"query": f"query_{i}", "limit": 10},
                    outputs={"results": [f"result_{i}"]},
                    metrics=StepMetrics(latency_ms=100),
                )
            )

        trace = get_current_trace()
        engine = JudgeEngine()
        pending = [s for s in trace.steps if s.evaluation.status == "pending"]
        engine._check_loops(trace, pending)

        flagged = [s for s in pending if "loop_detected" in s.evaluation.flags]
        assert len(flagged) == 0

    @pytest.mark.offline
    def test_loop_breaks_and_resumes(self, fresh_db):
        from agenttrace.judge import JudgeEngine
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, get_current_trace

        for query in ["same", "same", "different", "same", "same"]:
            add_step(
                TraceStep(
                    type="tool_execution",
                    name="search_api",
                    inputs={"query": query},
                    outputs={"results": []},
                    metrics=StepMetrics(latency_ms=100),
                )
            )

        trace = get_current_trace()
        engine = JudgeEngine()
        pending = [s for s in trace.steps if s.evaluation.status == "pending"]
        engine._check_loops(trace, pending)

        flagged = [s for s in pending if "loop_detected" in s.evaluation.flags]
        assert len(flagged) == 0, "Should not flag when loop is broken"

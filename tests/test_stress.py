"""
Test 4: Stress Test
Pushes AgentTrace storage to its limits with 50+ rapid trace steps.
No API calls needed.
"""

import sqlite3
import time

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


class TestHighVolumeSteps:
    """Validate SQLite handles high step counts without data loss."""

    @pytest.mark.stress
    @pytest.mark.offline
    def test_50_steps_persisted(self, fresh_db):
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step

        for i in range(50):
            step_type = ["llm_call", "tool_execution", "system_prompt"][i % 3]
            add_step(
                TraceStep(
                    type=step_type,
                    name=f"step_{i}",
                    inputs={"index": i, "data": f"input_payload_{i}" * 10},
                    outputs={"result": f"output_payload_{i}" * 10},
                    metrics=StepMetrics(latency_ms=i * 10, tokens_total=i * 50),
                )
            )

        steps = _get_steps(fresh_db, min_steps=50)
        assert len(steps) == 50

    @pytest.mark.stress
    @pytest.mark.offline
    def test_100_steps_persisted(self, fresh_db):
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step

        for i in range(100):
            add_step(
                TraceStep(
                    type="llm_call",
                    name=f"llm_step_{i}",
                    inputs={"prompt": f"Generate response #{i}"},
                    outputs={"content": f"Response #{i} " * 50},
                    metrics=StepMetrics(latency_ms=100 + i, tokens_total=200 + i * 10),
                )
            )

        steps = _get_steps(fresh_db, min_steps=100)
        assert len(steps) == 100

    @pytest.mark.stress
    @pytest.mark.offline
    def test_step_ordering_preserved(self, fresh_db):
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step

        for i in range(30):
            add_step(
                TraceStep(
                    type="tool_execution",
                    name=f"ordered_step_{i:03d}",
                    inputs={"seq": i},
                    outputs={"seq": i},
                    metrics=StepMetrics(latency_ms=10),
                )
            )

        steps = _get_steps(fresh_db, min_steps=30)
        names = [s["name"] for s in steps]
        expected = [f"ordered_step_{i:03d}" for i in range(30)]
        assert names == expected


class TestQueryPerformance:
    """Validate storage queries stay performant under load."""

    @pytest.mark.stress
    @pytest.mark.offline
    def test_list_traces_fast(self, fresh_db):
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, list_traces

        for i in range(50):
            add_step(
                TraceStep(
                    type="llm_call",
                    name=f"perf_step_{i}",
                    inputs={"data": "x" * 500},
                    outputs={"data": "y" * 500},
                    metrics=StepMetrics(latency_ms=100, tokens_total=500),
                )
            )

        start = time.time()
        traces = list_traces(limit=50)
        elapsed_ms = (time.time() - start) * 1000

        assert len(traces) >= 1
        assert elapsed_ms < 500, f"list_traces() took {elapsed_ms:.0f}ms"

    @pytest.mark.stress
    @pytest.mark.offline
    def test_get_trace_by_id_fast(self, fresh_db):
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, get_current_trace, get_trace_by_id

        for i in range(50):
            add_step(
                TraceStep(
                    type="tool_execution",
                    name=f"perf_step_{i}",
                    inputs={"i": i},
                    outputs={"r": i},
                    metrics=StepMetrics(latency_ms=50),
                )
            )

        trace = get_current_trace()
        start = time.time()
        result = get_trace_by_id(trace.trace_id)
        elapsed_ms = (time.time() - start) * 1000

        assert result is not None
        assert len(result.steps) == 50
        assert elapsed_ms < 500, f"get_trace_by_id() took {elapsed_ms:.0f}ms"


class TestDataIntegrity:
    """Validate data is not corrupted under high write load."""

    @pytest.mark.stress
    @pytest.mark.offline
    def test_large_payloads_stored(self, fresh_db):
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, get_current_trace

        add_step(
            TraceStep(
                type="llm_call",
                name="large_payload_step",
                inputs={"messages": [{"role": "user", "content": "x" * 2000}]},
                outputs={"content": "y" * 2000},
                metrics=StepMetrics(latency_ms=500, tokens_total=5000),
            )
        )

        trace = get_current_trace()
        assert len(trace.steps) >= 1
        assert trace.steps[-1].name == "large_payload_step"
        assert trace.steps[-1].metrics.tokens_total == 5000

    @pytest.mark.stress
    @pytest.mark.offline
    def test_step_types_correctly_stored(self, fresh_db):
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, get_current_trace

        types = ["llm_call", "tool_execution", "system_prompt", "server_crash"]
        for t in types:
            add_step(
                TraceStep(
                    type=t,
                    name=f"step_type_{t}",
                    inputs={"type": t},
                    outputs={"status": "ok"},
                    metrics=StepMetrics(),
                )
            )

        trace = get_current_trace()
        stored_types = {s.type for s in trace.steps}
        assert stored_types == set(types)

    @pytest.mark.stress
    @pytest.mark.offline
    def test_metrics_precision(self, fresh_db):
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, get_current_trace

        add_step(
            TraceStep(
                type="llm_call",
                name="precision_test",
                inputs={"test": True},
                outputs={"test": True},
                metrics=StepMetrics(latency_ms=12345, tokens_total=67890),
            )
        )

        trace = get_current_trace()
        step = trace.steps[-1]
        assert step.metrics.latency_ms == 12345
        assert step.metrics.tokens_total == 67890

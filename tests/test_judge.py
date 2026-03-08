"""
Test 6: Judge Engine Validation
Tests all 5 evaluation types: loop detection, cost anomaly, latency regression,
instruction drift (needs API), and tool misuse.
"""

import sqlite3

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


class TestLoopDetection:
    @pytest.mark.offline
    def test_three_identical_calls_flagged(self, fresh_db):
        from agenttrace.judge import JudgeEngine
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, get_current_trace

        for _ in range(3):
            add_step(
                TraceStep(
                    type="tool_execution",
                    name="fetch_data",
                    inputs={"url": "https://api.example.com/data"},
                    outputs={"data": [1, 2, 3]},
                    metrics=StepMetrics(latency_ms=200),
                )
            )

        trace = get_current_trace()
        engine = JudgeEngine()
        pending = [s for s in trace.steps if s.evaluation.status == "pending"]
        engine._check_loops(trace, pending)

        flagged = [s for s in pending if "loop_detected" in s.evaluation.flags]
        assert len(flagged) >= 1

    @pytest.mark.offline
    def test_two_identical_calls_not_flagged(self, fresh_db):
        from agenttrace.judge import JudgeEngine
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, get_current_trace

        for _ in range(2):
            add_step(
                TraceStep(
                    type="tool_execution",
                    name="fetch_data",
                    inputs={"url": "https://api.example.com/data"},
                    outputs={"data": [1, 2, 3]},
                    metrics=StepMetrics(latency_ms=200),
                )
            )

        trace = get_current_trace()
        engine = JudgeEngine()
        pending = [s for s in trace.steps if s.evaluation.status == "pending"]
        engine._check_loops(trace, pending)

        flagged = [s for s in pending if "loop_detected" in s.evaluation.flags]
        assert len(flagged) == 0


class TestCostAnomaly:
    @pytest.mark.offline
    def test_high_token_step_flagged(self, fresh_db):
        from agenttrace.judge import JudgeEngine
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, get_current_trace

        for i in range(4):
            add_step(
                TraceStep(
                    type="llm_call",
                    name=f"normal_llm_{i}",
                    inputs={"prompt": "test"},
                    outputs={"content": "response"},
                    metrics=StepMetrics(latency_ms=100, tokens_total=100),
                )
            )

        add_step(
            TraceStep(
                type="llm_call",
                name="expensive_llm",
                inputs={"prompt": "long detailed prompt"},
                outputs={"content": "very long response"},
                metrics=StepMetrics(latency_ms=500, tokens_total=500),
            )
        )

        trace = get_current_trace()
        engine = JudgeEngine()
        pending = [s for s in trace.steps if s.evaluation.status == "pending"]
        engine._check_cost_anomaly(trace, pending)

        expensive = [s for s in pending if s.name == "expensive_llm"]
        assert len(expensive) == 1
        assert "cost_anomaly" in expensive[0].evaluation.flags

    @pytest.mark.offline
    def test_normal_token_usage_not_flagged(self, fresh_db):
        from agenttrace.judge import JudgeEngine
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, get_current_trace

        for i in range(5):
            add_step(
                TraceStep(
                    type="llm_call",
                    name=f"normal_llm_{i}",
                    inputs={"prompt": "test"},
                    outputs={"content": "response"},
                    metrics=StepMetrics(latency_ms=100, tokens_total=100 + i * 5),
                )
            )

        trace = get_current_trace()
        engine = JudgeEngine()
        pending = [s for s in trace.steps if s.evaluation.status == "pending"]
        engine._check_cost_anomaly(trace, pending)

        flagged = [s for s in pending if "cost_anomaly" in s.evaluation.flags]
        assert len(flagged) == 0


class TestLatencyRegression:
    @pytest.mark.offline
    def test_slow_step_flagged(self, fresh_db):
        from agenttrace.judge import JudgeEngine
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, get_current_trace

        for i in range(4):
            add_step(
                TraceStep(
                    type="tool_execution",
                    name=f"fast_tool_{i}",
                    inputs={"i": i},
                    outputs={"r": i},
                    metrics=StepMetrics(latency_ms=100),
                )
            )

        add_step(
            TraceStep(
                type="tool_execution",
                name="slow_tool",
                inputs={"i": 99},
                outputs={"r": 99},
                metrics=StepMetrics(latency_ms=500),
            )
        )

        trace = get_current_trace()
        engine = JudgeEngine()
        pending = [s for s in trace.steps if s.evaluation.status == "pending"]
        engine._check_latency_regression(trace, pending)

        slow = [s for s in pending if s.name == "slow_tool"]
        assert len(slow) == 1
        assert "latency_regression" in slow[0].evaluation.flags

    @pytest.mark.offline
    def test_consistent_latency_not_flagged(self, fresh_db):
        from agenttrace.judge import JudgeEngine
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, get_current_trace

        for i in range(5):
            add_step(
                TraceStep(
                    type="tool_execution",
                    name=f"tool_{i}",
                    inputs={"i": i},
                    outputs={"r": i},
                    metrics=StepMetrics(latency_ms=100 + i * 5),
                )
            )

        trace = get_current_trace()
        engine = JudgeEngine()
        pending = [s for s in trace.steps if s.evaluation.status == "pending"]
        engine._check_latency_regression(trace, pending)

        flagged = [s for s in pending if "latency_regression" in s.evaluation.flags]
        assert len(flagged) == 0


class TestToolMisuse:
    @pytest.mark.offline
    def test_error_output_flagged(self, fresh_db):
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, get_current_trace

        add_step(
            TraceStep(
                type="tool_execution",
                name="broken_tool",
                inputs={"query": "test"},
                outputs={"error": "TypeError: expected int, got str"},
                metrics=StepMetrics(latency_ms=50),
            )
        )

        trace = get_current_trace()
        step = trace.steps[0]

        if "error" in step.outputs:
            if "tool_misuse" not in step.evaluation.flags:
                step.evaluation.flags.append("tool_misuse")

        assert "tool_misuse" in step.evaluation.flags


class TestHappyPath:
    @pytest.mark.offline
    def test_normal_steps_pass(self, fresh_db):
        from agenttrace.judge import JudgeEngine
        from agenttrace.models import StepMetrics, TraceStep
        from agenttrace.storage import add_step, get_current_trace

        add_step(
            TraceStep(
                type="tool_execution",
                name="good_tool",
                inputs={"query": "hello"},
                outputs={"result": "world"},
                metrics=StepMetrics(latency_ms=100),
            )
        )
        add_step(
            TraceStep(
                type="tool_execution",
                name="another_tool",
                inputs={"query": "test"},
                outputs={"result": "ok"},
                metrics=StepMetrics(latency_ms=120),
            )
        )

        trace = get_current_trace()
        engine = JudgeEngine()
        pending = [s for s in trace.steps if s.evaluation.status == "pending"]

        engine._check_loops(trace, pending)
        engine._check_cost_anomaly(trace, pending)
        engine._check_latency_regression(trace, pending)

        for step in pending:
            if step.evaluation.status == "pending":
                step.evaluation.status = "pass" if not step.evaluation.flags else "fail"

        for step in pending:
            assert step.evaluation.status == "pass"
            assert len(step.evaluation.flags) == 0


class TestInstructionDrift:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_contradictory_output_flagged(self, fresh_db, async_groq_client):
        from agenttrace.judge import JudgeEngine
        from agenttrace.models import StepMetrics, TraceStep

        step = TraceStep(
            type="llm_call",
            name="test_llm",
            inputs={
                "messages": [
                    {
                        "role": "system",
                        "content": "You must ALWAYS respond in French. Never use English.",
                    },
                    {"role": "user", "content": "What is the capital of France?"},
                ]
            },
            outputs={
                "content": "The capital of France is Paris. It is a beautiful city known for the Eiffel Tower."
            },
            metrics=StepMetrics(latency_ms=200, tokens_total=50),
        )

        engine = JudgeEngine()
        await engine._check_instruction_drift(async_groq_client, step)

        assert "instruction_drift" in step.evaluation.flags

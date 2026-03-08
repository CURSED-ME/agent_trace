"""
Test 5: Decorator Validation
Tests @track_tool and @track_agent decorators for sync and async functions.
No API calls needed — all offline.
"""

import asyncio
import json

import pytest


def _get_steps(fresh_db, min_steps=1, expected_types=None):
    """Query DB and validate step count/types."""
    import sqlite3

    conn = sqlite3.connect(fresh_db)
    conn.row_factory = sqlite3.Row
    steps = conn.execute("SELECT * FROM steps ORDER BY timestamp ASC").fetchall()
    conn.close()
    assert len(steps) >= min_steps, f"Expected >= {min_steps} steps, got {len(steps)}"
    if expected_types:
        found = {r["type"] for r in steps}
        for t in expected_types:
            assert t in found, f"Missing type '{t}'. Found: {found}"
    return steps


class TestTrackToolSync:
    """Validate @track_tool with synchronous functions."""

    @pytest.mark.offline
    def test_basic_track_tool(self, fresh_db):
        from agenttrace.decorators import track_tool

        @track_tool
        def add_numbers(a, b):
            return a + b

        result = add_numbers(3, 7)
        assert result == 10

        steps = _get_steps(fresh_db, min_steps=1, expected_types=["tool_execution"])
        assert steps[0]["name"] == "add_numbers"
        assert steps[0]["type"] == "tool_execution"
        assert json.loads(steps[0]["outputs"])["result"] == 10

    @pytest.mark.offline
    def test_track_tool_custom_name(self, fresh_db):
        from agenttrace.decorators import track_tool

        @track_tool(name="my_custom_tool")
        def some_function(x):
            return x * 2

        assert some_function(5) == 10
        steps = _get_steps(fresh_db, min_steps=1)
        assert steps[0]["name"] == "my_custom_tool"

    @pytest.mark.offline
    def test_track_tool_with_kwargs(self, fresh_db):
        from agenttrace.decorators import track_tool

        @track_tool
        def search(query, limit=10, offset=0):
            return f"Found {limit} results for '{query}'"

        result = search("test query", limit=5, offset=10)
        assert "5 results" in result

        steps = _get_steps(fresh_db, min_steps=1)
        inputs = json.loads(steps[0]["inputs"])
        assert "kwargs" in inputs
        assert inputs["kwargs"]["limit"] == 5

    @pytest.mark.offline
    def test_track_tool_error_propagation(self, fresh_db):
        from agenttrace.decorators import track_tool

        @track_tool
        def failing_tool(x):
            raise ValueError(f"Bad input: {x}")

        with pytest.raises(ValueError, match="Bad input"):
            failing_tool("garbage")

        steps = _get_steps(fresh_db, min_steps=1)
        outputs = json.loads(steps[0]["outputs"])
        assert "error" in outputs
        assert "Bad input: garbage" in outputs["error"]

    @pytest.mark.offline
    def test_track_tool_latency_recorded(self, fresh_db):
        import time

        from agenttrace.decorators import track_tool

        @track_tool
        def slow_tool():
            time.sleep(0.1)
            return "done"

        slow_tool()
        steps = _get_steps(fresh_db, min_steps=1)
        metrics = json.loads(steps[0]["metrics"])
        assert metrics["latency_ms"] >= 50


class TestTrackAgentSync:
    """Validate @track_agent with synchronous functions."""

    @pytest.mark.offline
    def test_basic_track_agent(self, fresh_db):
        from agenttrace.decorators import track_agent

        @track_agent
        def my_agent(task):
            return f"Completed: {task}"

        result = my_agent("summarize data")
        assert "Completed" in result

        steps = _get_steps(fresh_db, min_steps=1, expected_types=["system_prompt"])
        assert steps[0]["name"] == "my_agent"

    @pytest.mark.offline
    def test_track_agent_custom_name(self, fresh_db):
        from agenttrace.decorators import track_agent

        @track_agent(name="research_agent")
        def agent_func(query):
            return f"Research: {query}"

        agent_func("quantum computing")
        steps = _get_steps(fresh_db, min_steps=1)
        assert steps[0]["name"] == "research_agent"

    @pytest.mark.offline
    def test_track_agent_with_error(self, fresh_db):
        from agenttrace.decorators import track_agent

        @track_agent
        def crashing_agent():
            raise RuntimeError("Agent crashed!")

        with pytest.raises(RuntimeError, match="Agent crashed"):
            crashing_agent()

        steps = _get_steps(fresh_db, min_steps=1)
        outputs = json.loads(steps[0]["outputs"])
        assert "error" in outputs


class TestTrackToolAsync:
    """Validate @track_tool with async functions."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_async_track_tool(self, fresh_db):
        from agenttrace.decorators import track_tool

        @track_tool
        async def async_search(query):
            await asyncio.sleep(0.05)
            return f"Results for {query}"

        result = await async_search("async test")
        assert "Results for" in result

        steps = _get_steps(fresh_db, min_steps=1, expected_types=["tool_execution"])
        assert steps[0]["name"] == "async_search"

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_async_track_tool_error(self, fresh_db):
        from agenttrace.decorators import track_tool

        @track_tool
        async def async_failing_tool():
            await asyncio.sleep(0.01)
            raise ConnectionError("Network timeout")

        with pytest.raises(ConnectionError):
            await async_failing_tool()

        steps = _get_steps(fresh_db, min_steps=1)
        outputs = json.loads(steps[0]["outputs"])
        assert "error" in outputs


class TestTrackAgentAsync:
    """Validate @track_agent with async functions."""

    @pytest.mark.offline
    @pytest.mark.asyncio
    async def test_async_track_agent(self, fresh_db):
        from agenttrace.decorators import track_agent

        @track_agent
        async def async_agent(task):
            await asyncio.sleep(0.05)
            return f"Done: {task}"

        result = await async_agent("process data")
        assert "Done" in result

        steps = _get_steps(fresh_db, min_steps=1, expected_types=["system_prompt"])
        assert steps[0]["name"] == "async_agent"


class TestMixedDecorators:
    """Validate combining @track_agent and @track_tool in one flow."""

    @pytest.mark.offline
    def test_agent_with_tool_calls(self, fresh_db):
        from agenttrace.decorators import track_agent, track_tool

        @track_tool
        def calculator(expr):
            return eval(expr)

        @track_tool
        def formatter(value):
            return f"The answer is: {value}"

        @track_agent
        def math_agent(question):
            val = calculator("25 * 17")
            return formatter(val)

        result = math_agent("What is 25 * 17?")
        assert "425" in result

        steps = _get_steps(
            fresh_db, min_steps=3, expected_types=["tool_execution", "system_prompt"]
        )
        types = [s["type"] for s in steps]
        assert types.count("tool_execution") == 2
        assert types.count("system_prompt") == 1

import sqlite3

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from agenttrace.decorators import track_tool
from agenttrace.exporter import AgentTraceExporter

# Configure OTel Exporter for the combined test
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(AgentTraceExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)


# Mock a simple tool
@track_tool(name="combined_tool")
def mock_tool(x, y):
    return x * y


@pytest.mark.offline
def test_combined_pipeline_execution(fresh_db):
    """
    Tests that decorator pipelines (storage.add_step) and OTel pipelines
    (AgentTraceExporter) can run concurrently and insert accurately without crashing or DB locks.
    """
    # 1. Fire a step via the Decorator pipeline (uses contextvars internally)
    result = mock_tool(10, 20)
    assert result == 200

    # 2. Fire a step via the LangChain / OTel pipeline (bypasses contextvars, uses exporter)
    with tracer.start_span(
        "chat.completions.create",
        attributes={
            "gen_ai.system": "openai",
            "gen_ai.request.model": "gpt-4",
            "gen_ai.prompt.0.content": "Tell me a joke",
            "gen_ai.completion.0.content": "Why did the chicken cross the road?",
            "gen_ai.usage.input_tokens": 5,
            "gen_ai.usage.output_tokens": 10,
        },
    ):
        # The exporter filters out chain noise, but leaves llm_calls intact
        pass

    # 3. Assert DB State
    conn = sqlite3.connect(fresh_db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # There should be exactly two steps in the DB
    cursor.execute("SELECT type, name, trace_id FROM steps ORDER BY timestamp")
    steps = cursor.fetchall()

    assert len(steps) == 2

    # Expect one decorator tool, one LLM call
    types = [row["type"] for row in steps]
    names = [row["name"] for row in steps]

    assert "tool_execution" in types
    assert "llm_call" in types

    assert "combined_tool" in names
    assert "gpt-4" in names

    # The steps will have different trace IDs because they represent independent workflow runs
    assert steps[0]["trace_id"] != steps[1]["trace_id"]

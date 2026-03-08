import os
import sqlite3
import time

import pytest

import agenttrace.auto  # noqa: F401, vital for OTel span processor to start


def test_direct_openai_instrumentation(fresh_db):
    """
    Test the opentelemetry-instrumentation-openai wrapper.
    Uses the OpenAI Python SDK pointing to Groq's OpenAI-compatible API to verify real network callbacks.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key or api_key == "your_groq_api_key_here":
        pytest.skip("GROQ_API_KEY not set - skipping E2E OpenAI SDK test")

    try:
        from openai import OpenAI
    except ImportError:
        pytest.skip("openai package not installed")

    client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": "Explain OpenTelemetry concisely."}],
        max_tokens=20,
    )

    assert response.choices[0].message.content

    time.sleep(0.5)  # Wait for SimpleSpanProcessor to sync to SQLite

    conn = sqlite3.connect(fresh_db)
    conn.row_factory = sqlite3.Row
    steps = conn.execute("SELECT * FROM steps WHERE type = 'llm_call'").fetchall()

    if len(steps) != 1:
        all_steps = [dict(r) for r in conn.execute("SELECT * FROM steps").fetchall()]
        pytest.fail(
            f"Expected 1 llm_call step, found {len(steps)}. All DB steps: {all_steps}"
        )

    step = steps[0]
    print(f"\n\n--- DUMP ---\n{dict(step)}\n--- END ---\n")

    import json

    parsed_inputs = json.loads(step["inputs"])
    parsed_outputs = json.loads(step["outputs"])

    assert step["name"] == "llama-3.1-8b-instant"
    assert "Explain OpenTelemetry concisely." in parsed_inputs["messages"][0]["content"]
    assert response.choices[0].message.content == parsed_outputs["content"]

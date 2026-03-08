"""
Test 1: ReAct Agent with Real Tools
A real ReAct-style agent loop using Groq's OpenAI-compatible API.
Requires GROQ_API_KEY in .env.
"""

import json
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


@pytest.mark.integration
class TestReActAgent:
    """Full ReAct loop: LLM decides tool → tool executes → LLM synthesizes."""

    def test_react_loop_with_tools(self, fresh_db, groq_client):
        from agenttrace.decorators import track_tool

        @track_tool
        def calculator(expression: str) -> str:
            try:
                result = eval(expression, {"__builtins__": {}})
                return str(result)
            except Exception as e:
                return f"Error: {e}"

        @track_tool
        def lookup(topic: str) -> str:
            facts = {
                "earth_radius": "The Earth's radius is approximately 6,371 km.",
                "speed_of_light": "The speed of light is 299,792,458 m/s.",
            }
            return facts.get(topic, f"No information found for '{topic}'.")

        # Step 1: Ask the LLM what to do
        groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a ReAct agent. Given a question, respond with EXACTLY:\n"
                        "ACTION: calculator(expression)\nDo not add any other text."
                    ),
                },
                {"role": "user", "content": "What is 25 multiplied by 17?"},
            ],
            temperature=0.0,
        )

        # Step 2: Execute the tool
        tool_result = calculator("25 * 17")

        # Step 3: Call LLM again
        groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Give a concise final answer."},
                {"role": "user", "content": "What is 25 multiplied by 17?"},
                {"role": "assistant", "content": f"Calculator result: {tool_result}"},
                {"role": "user", "content": "Give the final answer in one sentence."},
            ],
            temperature=0.0,
        )

        # Validate tool call was captured
        steps = _get_steps(fresh_db, min_steps=1, expected_types=["tool_execution"])
        tool_steps = [s for s in steps if s["type"] == "tool_execution"]
        assert len(tool_steps) >= 1

        outputs = json.loads(tool_steps[0]["outputs"])
        assert outputs.get("result") == "425"

    def test_react_with_multiple_tools(self, fresh_db, groq_client):
        from agenttrace.decorators import track_tool

        @track_tool
        def get_temperature(city: str) -> str:
            temps = {"paris": "22°C", "tokyo": "28°C", "london": "15°C"}
            return temps.get(city.lower(), "Unknown city")

        @track_tool
        def convert_celsius_to_fahrenheit(celsius_str: str) -> str:
            num = float(celsius_str.replace("°C", ""))
            f = (num * 9 / 5) + 32
            return f"{f}°F"

        temp = get_temperature("Paris")
        temp_f = convert_celsius_to_fahrenheit(temp)

        groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Give a brief weather report."},
                {"role": "user", "content": f"Paris temperature: {temp} ({temp_f})"},
            ],
            temperature=0.0,
        )

        steps = _get_steps(fresh_db, min_steps=2)
        tool_steps = [s for s in steps if s["type"] == "tool_execution"]
        assert len(tool_steps) == 2

        tool_names = {s["name"] for s in tool_steps}
        assert "get_temperature" in tool_names
        assert "convert_celsius_to_fahrenheit" in tool_names


@pytest.mark.integration
class TestStreamingCapture:
    def test_streaming_response_no_crash(self, fresh_db, groq_client):
        """Streaming completion doesn't crash AgentTrace."""
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Count from 1 to 5."},
            ],
            stream=True,
            temperature=0.0,
        )

        chunks = []
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                chunks.append(chunk.choices[0].delta.content)

        full_response = "".join(chunks)
        assert len(full_response) > 0, "Stream produced no output"

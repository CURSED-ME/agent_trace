"""
Test 2: Multi-Step Research Chain
A chained multi-step pipeline: generate queries → search → summarize → rewrite.
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
class TestMultiStepChain:
    def test_research_pipeline(self, fresh_db, groq_client):
        from agenttrace.decorators import track_agent, track_tool

        @track_tool
        def web_search(query: str) -> str:
            mock_results = {
                "quantum computing applications": [
                    "Quantum computing is used in drug discovery.",
                    "Financial modeling uses quantum algorithms.",
                ],
                "quantum computing risks": [
                    "Quantum computers threaten current encryption.",
                    "The technology is still in early stages.",
                ],
            }
            for key, results in mock_results.items():
                if key in query.lower():
                    return "\n".join(results)
            return "No results found for: " + query

        @track_agent(name="research_agent")
        def run_research(question: str) -> str:
            # Step 1: Generate queries
            query_response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": "Generate exactly 2 search queries. Return each on a new line.",
                    },
                    {"role": "user", "content": question},
                ],
                temperature=0.0,
            )
            queries = query_response.choices[0].message.content.strip().split("\n")
            queries = [q.strip() for q in queries if q.strip()][:2]

            # Step 2: Search
            all_results = []
            for q in queries:
                results = web_search(q)
                all_results.append(f"Query: {q}\nResults:\n{results}")

            combined = "\n\n".join(all_results)

            # Step 3: Summarize
            summary_resp = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "Summarize in 2-3 sentences."},
                    {"role": "user", "content": combined},
                ],
                temperature=0.0,
            )
            summary = summary_resp.choices[0].message.content.strip()

            # Step 4: Final report
            report_resp = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": "Rewrite as a professional research brief.",
                    },
                    {"role": "user", "content": summary},
                ],
                temperature=0.0,
            )
            return report_resp.choices[0].message.content.strip()

        report = run_research(
            "What are the applications and risks of quantum computing?"
        )
        assert len(report) > 50

        steps = _get_steps(
            fresh_db, min_steps=3, expected_types=["tool_execution", "system_prompt"]
        )
        tool_steps = [s for s in steps if s["type"] == "tool_execution"]
        assert len(tool_steps) >= 2

    def test_chain_with_error_recovery(self, fresh_db, groq_client):
        from agenttrace.decorators import track_tool

        call_count = {"n": 0}

        @track_tool
        def flaky_api(query: str) -> str:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ConnectionError("API temporarily unavailable")
            return f"Results for: {query}"

        try:
            flaky_api("test query")
        except ConnectionError:
            pass

        result = flaky_api("test query")
        assert "Results for" in result

        groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Summarize the data."},
                {"role": "user", "content": result},
            ],
            temperature=0.0,
        )

        steps = _get_steps(fresh_db, min_steps=2)
        tool_steps = [s for s in steps if s["type"] == "tool_execution"]
        assert len(tool_steps) == 2

        out1 = json.loads(tool_steps[0]["outputs"])
        out2 = json.loads(tool_steps[1]["outputs"])
        assert "error" in out1
        assert "result" in out2

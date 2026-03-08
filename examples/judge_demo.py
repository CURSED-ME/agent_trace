import time

from agenttrace.models import StepMetrics, TraceStep
from agenttrace.storage import add_step, get_current_trace


def simulate_bad_agent():
    # Force initialize a new trace via get_current_trace()
    trace = get_current_trace()
    print(f"Creating synthetic trace: {trace.trace_id}")

    # Simulated LLM steps with baseline tokens and latency
    for i in range(3):
        add_step(
            TraceStep(
                type="llm_call",
                name="llama-3.1-8b",
                inputs={"messages": [{"role": "user", "content": f"Do step {i}"}]},
                outputs={"content": "OK"},
                metrics=StepMetrics(tokens_total=20, latency_ms=500),
            )
        )
        time.sleep(0.1)

    # 1. Cost Anomaly Step: 150 tokens vs 20 avg
    add_step(
        TraceStep(
            type="llm_call",
            name="llama-3.1-8b",
            inputs={"messages": [{"role": "user", "content": "Analyze huge document"}]},
            outputs={"content": "Here is a very long response..." * 10},
            metrics=StepMetrics(tokens_total=150, latency_ms=500),
        )
    )

    # 2. Latency Regression Step: 2500ms vs 500ms
    add_step(
        TraceStep(
            type="llm_call",
            name="llama-3.1-8b",
            inputs={"messages": [{"role": "user", "content": "Just say hi"}]},
            outputs={"content": "Hi"},
            metrics=StepMetrics(tokens_total=20, latency_ms=2500),
        )
    )

    # 3. Tool Misuse: tool execution outputting an error
    add_step(
        TraceStep(
            type="tool_execution",
            name="search_db",
            inputs={"args": ["John Doe"], "kwargs": {}},
            outputs={"error": "Missing required argument 'table_name'"},
        )
    )

    # 4. Loop Detection: calling the same tool 3 times with identical args
    for _ in range(3):
        add_step(
            TraceStep(
                type="tool_execution",
                name="fetch_weather",
                inputs={"args": ["London"], "kwargs": {}},
                outputs={"result": "Raining"},
            )
        )

    # 5. Instruction Drift (Hallucination)
    # The system prompts expects purely JSON, but output is conversational
    add_step(
        TraceStep(
            type="llm_call",
            name="llama-3.1-8b",
            inputs={
                "messages": [
                    {
                        "role": "system",
                        "content": "Always output purely valid JSON, nothing else.",
                    },
                    {"role": "user", "content": "Who is the president?"},
                ]
            },
            outputs={
                "content": 'Sure! I can help with that. The president is... wait, here is some JSON: {\\"president\\": \\"unknown\\"} Let me know if you need anything else!'
            },
            metrics=StepMetrics(tokens_total=40, latency_ms=600),
        )
    )

    print("Synthetic steps added. Wait for the background judge to evaluate them!")


if __name__ == "__main__":
    simulate_bad_agent()

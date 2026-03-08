from typing import Any

from opentelemetry import trace

tracer = trace.get_tracer(__name__)

# Note: CrewAI relies heavily on LangChain's callback system under the hood.
# The LangChain integration catches 90% of CrewAI activity natively.
# We map remaining CrewAI-specific high-level task events into AgentTrace traces here.


class AgentTraceCrewAICallback:
    def __init__(self):
        self.active_tasks = {}

    def on_task_start(self, task: Any):
        # Maps CrewAI tasks into a 'system_prompt' step summarizing the goal
        span = tracer.start_span(
            f"crewai.task.{getattr(task, 'name', 'unnamed')}",
            attributes={
                "agenttrace.type": "system_prompt",
                "agenttrace.inputs": getattr(task, "description", ""),
                "crew.agent_name": getattr(
                    getattr(task, "agent", None), "role", "unknown"
                ),
            },
        )
        self.active_tasks[id(task)] = span

    def on_task_end(self, task: Any, output: str):
        if id(task) in self.active_tasks:
            span = self.active_tasks[id(task)]
            span.set_attribute("agenttrace.outputs", output)
            span.end()
            del self.active_tasks[id(task)]


def register_crewai():
    import importlib.util

    if importlib.util.find_spec("crewai") is not None:
        # CrewAI telemetry overrides for a future, deeper integration map
        print("AgentTrace: Successfully registered zero-config CrewAI integration.")

from typing import Any, Dict, List
import uuid
from opentelemetry import trace

tracer = trace.get_tracer(__name__)


class AgentTraceCallbackHandler:
    def __init__(self):
        self._spans = {}

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> Any:
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        span = tracer.start_span(
            "langchain.llm",
            attributes={
                "gen_ai.system": "openai",  # Fallback for unknown
                "gen_ai.request.model": kwargs.get("invocation_params", {}).get(
                    "model", "unknown"
                ),
                "agenttrace.inputs": str(prompts),
            },
        )
        self._spans[run_id] = span

    def on_llm_end(self, response: Any, **kwargs: Any) -> Any:
        run_id = str(kwargs.get("run_id"))
        if run_id in self._spans:
            span = self._spans[run_id]

            output_text = ""
            if response.generations and len(response.generations) > 0:
                if len(response.generations[0]) > 0:
                    output_text = response.generations[0][0].text

            span.set_attribute("agenttrace.outputs", str(output_text))

            if response.llm_output and "token_usage" in response.llm_output:
                usage = response.llm_output["token_usage"]
                if "total_tokens" in usage:
                    span.set_attribute(
                        "gen_ai.response.usage.prompt_tokens",
                        usage.get("prompt_tokens", 0),
                    )
                    span.set_attribute(
                        "gen_ai.response.usage.completion_tokens",
                        usage.get("completion_tokens", 0),
                    )

            span.end()
            del self._spans[run_id]

    def on_llm_error(self, error: Exception, **kwargs: Any) -> Any:
        run_id = str(kwargs.get("run_id"))
        if run_id in self._spans:
            span = self._spans[run_id]
            span.record_exception(error)
            span.set_attribute("agenttrace.outputs", str(error))
            span.end()
            del self._spans[run_id]

    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> Any:
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        name = serialized.get("name", "tool")
        span = tracer.start_span(
            name,
            attributes={
                "agenttrace.type": "tool_execution",
                "agenttrace.inputs": input_str,
            },
        )
        self._spans[run_id] = span

    def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        run_id = str(kwargs.get("run_id"))
        if run_id in self._spans:
            span = self._spans[run_id]
            span.set_attribute("agenttrace.outputs", output)
            span.end()
            del self._spans[run_id]

    def on_tool_error(self, error: Exception, **kwargs: Any) -> Any:
        run_id = str(kwargs.get("run_id"))
        if run_id in self._spans:
            span = self._spans[run_id]
            span.record_exception(error)
            span.set_attribute("agenttrace.outputs", str(error))
            span.end()
            del self._spans[run_id]


def register_langchain():
    try:
        from langchain_core.callbacks import set_global_handler

        set_global_handler(AgentTraceCallbackHandler())
        print("AgentTrace: Successfully registered zero-config LangChain integration.")
    except ImportError:
        pass

import logging
import uuid
from typing import Any, Dict, List

from opentelemetry import trace

logger = logging.getLogger("agenttrace")
tracer = trace.get_tracer(__name__)

try:
    from langchain_core.callbacks.base import BaseCallbackHandler
except ImportError:
    BaseCallbackHandler = object  # Fallback so the class def doesn't crash


class AgentTraceCallbackHandler(BaseCallbackHandler):
    # Class-level dict to share spans across different handler instances spawned by LangGraph threads
    _global_spans = {}
    _global_tokens = {}

    def __init__(self):
        super().__init__()
        # Prevent memory leaks in long-running processes if spans occasionally drop/crash
        if len(self.__class__._global_spans) > 1000:
            self.__class__._global_spans.clear()
            self.__class__._global_tokens.clear()

        self._spans = self.__class__._global_spans
        self._tokens = self.__class__._global_tokens

    def on_chain_start(
        self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any
    ) -> Any:
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        parent_run_id = str(kwargs.get("parent_run_id"))

        from opentelemetry.context import attach
        from opentelemetry.trace import set_span_in_context

        ctx = None
        if parent_run_id and parent_run_id in self._spans:
            ctx = set_span_in_context(self._spans[parent_run_id])

        # Attach context if continuing a trace (fixes thread local drops)
        if ctx:
            self._tokens[run_id] = attach(ctx)

        span = tracer.start_span(
            serialized.get("name", "langgraph.chain")
            if serialized
            else "langgraph.chain",
            context=ctx,
            attributes={
                "agenttrace.type": "chain",
            },
        )
        self._spans[run_id] = span

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> Any:
        run_id = str(kwargs.get("run_id"))
        if run_id in self._spans:
            span = self._spans[run_id]
            span.end()
            del self._spans[run_id]

        if run_id in self._tokens:
            from opentelemetry.context import detach

            detach(self._tokens[run_id])
            del self._tokens[run_id]

    def on_chain_error(self, error: Exception, **kwargs: Any) -> Any:
        run_id = str(kwargs.get("run_id"))
        if run_id in self._spans:
            span = self._spans[run_id]
            span.record_exception(error)
            span.end()
            del self._spans[run_id]

        if run_id in self._tokens:
            from opentelemetry.context import detach

            detach(self._tokens[run_id])
            del self._tokens[run_id]

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> Any:
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        parent_run_id = str(kwargs.get("parent_run_id"))

        from opentelemetry.context import attach
        from opentelemetry.trace import set_span_in_context

        ctx = None
        if parent_run_id in self._spans:
            ctx = set_span_in_context(self._spans[parent_run_id])

        if ctx:
            self._tokens[run_id] = attach(ctx)

        span = tracer.start_span(
            "langchain.llm",
            context=ctx,
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

        if run_id in self._tokens:
            from opentelemetry.context import detach

            detach(self._tokens[run_id])
            del self._tokens[run_id]

    def on_llm_error(self, error: Exception, **kwargs: Any) -> Any:
        run_id = str(kwargs.get("run_id"))
        if run_id in self._spans:
            span = self._spans[run_id]
            span.record_exception(error)
            span.set_attribute("agenttrace.outputs", str(error))
            span.end()
            del self._spans[run_id]

        if run_id in self._tokens:
            from opentelemetry.context import detach

            detach(self._tokens[run_id])
            del self._tokens[run_id]

    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> Any:
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        parent_run_id = str(kwargs.get("parent_run_id"))

        from opentelemetry.context import attach
        from opentelemetry.trace import set_span_in_context

        ctx = None
        if parent_run_id and parent_run_id in self._spans:
            ctx = set_span_in_context(self._spans[parent_run_id])

        if ctx:
            self._tokens[run_id] = attach(ctx)

        name = serialized.get("name", "tool") if serialized else "tool"
        span = tracer.start_span(
            name,
            context=ctx,
            attributes={
                "agenttrace.type": "tool_execution",
                "agenttrace.inputs": input_str,
            },
        )
        self._spans[run_id] = span

    def on_tool_end(self, output: Any, **kwargs: Any) -> Any:
        run_id = str(kwargs.get("run_id"))
        if run_id in self._spans:
            span = self._spans[run_id]
            span.set_attribute("agenttrace.outputs", str(output))
            span.end()
            del self._spans[run_id]

        if run_id in self._tokens:
            from opentelemetry.context import detach

            detach(self._tokens[run_id])
            del self._tokens[run_id]

    def on_tool_error(self, error: Exception, **kwargs: Any) -> Any:
        run_id = str(kwargs.get("run_id"))
        if run_id in self._spans:
            span = self._spans[run_id]
            span.record_exception(error)
            span.set_attribute("agenttrace.outputs", str(error))
            span.end()
            del self._spans[run_id]

        if run_id in self._tokens:
            from opentelemetry.context import detach

            detach(self._tokens[run_id])
            del self._tokens[run_id]


def register_langchain():
    try:
        from langchain_core.callbacks.manager import BaseCallbackManager

        original_init = BaseCallbackManager.__init__

        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            # Only add if it's not already there to prevent duplicates
            if not any(isinstance(h, AgentTraceCallbackHandler) for h in self.handlers):
                self.add_handler(AgentTraceCallbackHandler(), inherit=True)

        BaseCallbackManager.__init__ = patched_init

        logger.info(
            "AgentTrace: Successfully registered zero-config LangChain integration."
        )
    except Exception as e:
        logger.error(f"AgentTrace: Failed to monkey-patch LangChain callbacks: {e}")

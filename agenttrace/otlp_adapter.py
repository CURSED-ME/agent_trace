import json
import logging
from typing import Any, Dict, List, Optional

from .models import StepMetrics, TraceStep

logger = logging.getLogger("agenttrace")


def _get_attribute(
    attributes: Dict[str, Any], keys: List[str], default: Any = None
) -> Any:
    for key in keys:
        if key in attributes:
            return attributes[key]
    return default


def process_span(
    name: str,
    attributes: Dict[str, Any],
    events: List[Dict[str, Any]],
    start_time_unix_nano: int,
    end_time_unix_nano: int,
    trace_id_hex: str,
    span_id_hex: str,
    parent_span_id_hex: Optional[str] = None,
) -> Optional[TraceStep]:
    """
    Normalizes a generic OTel Span into an AgentTrace TraceStep.
    Handles semantic convention differences between Python and Node.js SDKs.
    """
    try:
        # Check if we should process this span
        is_llm_span = name in [
            "chat.completions.create",
            "chat.completions.create.stream",
            "messages.create",  # Anthropic
            "messages.create.stream",  # Anthropic streaming
        ]
        is_agenttrace = "agenttrace" in name or "agenttrace.type" in attributes
        is_genai = any(
            key.startswith("gen_ai.") or key.startswith("llm.") or key.startswith("ai.")
            for key in attributes.keys()
        )
        is_vercel_ai = name.startswith("ai.")

        if not (is_llm_span or is_agenttrace or is_genai or is_vercel_ai):
            return None

        # Extract GenAI semantic conventions (fallback to Vercel formats if not found)
        # Handle variations between Node.js and Python OTel instrumentations
        system = _get_attribute(attributes, ["gen_ai.system", "llm.system", "ai.model.provider"], "unknown")
        model = _get_attribute(
            attributes,
            ["gen_ai.request.model", "llm.request.model", "llm.model_name", "ai.model.id"],
            "unknown",
        )
        input_tokens = _get_attribute(
            attributes, ["gen_ai.usage.input_tokens", "llm.usage.prompt_tokens", "ai.usage.promptTokens", "ai.usage.inputTokens"], 0
        )
        output_tokens = _get_attribute(
            attributes, ["gen_ai.usage.output_tokens", "llm.usage.completion_tokens", "ai.usage.completionTokens", "ai.usage.outputTokens"], 0
        )
        total_tokens = input_tokens + output_tokens

        # Map OTel spans to our TraceStep model
        step_type = "llm_call"
        step_name = model if system != "unknown" else name

        # Handle decorator spans
        if attributes.get("agenttrace.type"):
            step_type = attributes.get("agenttrace.type")
            step_name = name.replace("agenttrace.", "")

        # Handle Vercel outer wrapper spans (like ai.generateText, ai.streamText)
        # Tested against Vercel AI SDK v3.4.0+ & ai@6.0+ experimental telemetry
        if is_vercel_ai and not name.endswith(".doGenerate") and not name.endswith(".doStream"):
            step_type = "tool"
            step_name = attributes.get("ai.telemetry.functionId", name)
            if attributes.get("ai.telemetry.metadata.agent"):
                step_type = "agent"
                step_name = attributes.get("ai.telemetry.metadata.agent")

        # Handle Vercel inner tool span
        if name == "ai.toolCall":
            step_type = "tool"
            step_name = attributes.get("ai.toolCall.name", "unknown_tool")

        # Filter out LangGraph internal orchestration chains from clogging the UI
        if step_type == "chain" and step_name == "langgraph.chain":
            return None

        latency_ms = 0
        if end_time_unix_nano and start_time_unix_nano:
            latency_ms = int((end_time_unix_nano - start_time_unix_nano) / 1000000)

        # Try to extract prompts & completions
        inputs: dict = {"model": model, "messages": []}
        outputs: dict = {"content": ""}

        # Check if inputs/outputs were set via attributes (like our LangChain adapter does)
        if "agenttrace.inputs" in attributes:
            inputs["messages"].append({"content": attributes["agenttrace.inputs"]})
        if "agenttrace.outputs" in attributes:
            outputs["content"] = attributes["agenttrace.outputs"]

        # Parse Events
        for event in events:
            evt_name = event.get("name", "")
            evt_attributes = event.get("attributes", {})

            if evt_name == "gen_ai.content.prompt":
                inputs["messages"].append(
                    {"content": evt_attributes.get("gen_ai.prompt")}
                )
            elif evt_name == "gen_ai.content.completion":
                outputs["content"] += str(evt_attributes.get("gen_ai.completion", ""))
            elif evt_name == "agenttrace.inputs":
                payload = evt_attributes.get("payload", "{}")
                if isinstance(payload, str):
                    try:
                        parsed = json.loads(payload)
                        inputs = parsed if isinstance(parsed, dict) else {"raw": parsed}
                    except json.JSONDecodeError:
                        inputs = {"raw": payload}
                elif isinstance(payload, dict):
                    inputs = payload
            elif evt_name == "agenttrace.outputs":
                payload = evt_attributes.get("payload", "{}")
                if isinstance(payload, str):
                    try:
                        parsed = json.loads(payload)
                        outputs = parsed if isinstance(parsed, dict) else {"raw": parsed}
                    except json.JSONDecodeError:
                        outputs = {"raw": payload}
                elif isinstance(payload, dict):
                    outputs = payload
            elif evt_name == "exception":
                outputs = {
                    "error": evt_attributes.get("exception.message", "Unknown Error"),
                    "stacktrace": evt_attributes.get("exception.stacktrace"),
                }

        # Fallback for older semantic conventions or Vercel specific keys
        if "messages" in inputs and getattr(inputs, "get", lambda x, y: None)("messages") == [] and not attributes.get("agenttrace.type"):
            prompt_content = _get_attribute(attributes, ["gen_ai.prompt.0.content", "ai.prompt.messages", "ai.prompt"])
            if prompt_content:
                inputs["messages"] = [{"content": prompt_content}]

            completion_content = _get_attribute(attributes, ["gen_ai.completion.0.content", "ai.response.text"])
            if completion_content:
                outputs["content"] = completion_content

        # Extract Vercel Tool Call payload
        if name == "ai.toolCall":
            ai_args = attributes.get("ai.toolCall.args")
            if ai_args:
                try:
                    inputs = json.loads(ai_args)
                except json.JSONDecodeError:
                    inputs = {"raw_args": ai_args}

            ai_result = attributes.get("ai.toolCall.result")
            if ai_result:
                try:
                    outputs = json.loads(ai_result)
                except json.JSONDecodeError:
                    outputs = {"raw_result": ai_result}

        # Extract telemetry metadata
        metadata = None
        ai_metadata = {k.replace("ai.telemetry.metadata.", ""): v for k, v in attributes.items() if k.startswith("ai.telemetry.metadata.")}
        if ai_metadata:
            metadata = ai_metadata

        # Extract Error status explicitly if not captured by events
        error_msg = None
        if "error" in outputs:
            error_msg = outputs["error"]
        elif attributes.get("status.code") == 2: # OTel ERROR code
            error_msg = attributes.get("status.message", "Unknown Span Error")

        step = TraceStep(
            step_id=span_id_hex,
            type=step_type,
            name=step_name,
            inputs=inputs,
            outputs=outputs,
            error=error_msg,
            metadata=metadata,
            metrics=StepMetrics(latency_ms=latency_ms, tokens_total=total_tokens),
        )

        # Store context propagation attributes in the step definition so storage layer can use it if needed
        # We can pass these down via a separate dict or attach them dynamically
        setattr(step, "_trace_id", trace_id_hex)
        setattr(step, "_span_id", span_id_hex)
        setattr(step, "_parent_span_id", parent_span_id_hex)

        return step
    except Exception as e:
        logger.warning(
            f"OTLP Adapter Error processing span '{name}': {e}", exc_info=True
        )
        return None

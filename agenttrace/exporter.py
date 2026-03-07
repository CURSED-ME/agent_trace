from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
import json
from .models import TraceStep, StepMetrics
from .storage import add_step


class AgentTraceExporter(SpanExporter):
    def export(self, spans):
        for span in spans:
            # We only want to log LLM calls from semantic conventions or our decorators/integrations
            is_openai = span.name in [
                "chat.completions.create",
                "chat.completions.create.stream",
            ]
            is_agenttrace = "agenttrace" in span.name or (
                span.attributes and "agenttrace.type" in span.attributes
            )
            is_genai = span.attributes and "gen_ai.system" in span.attributes

            if not (is_openai or is_agenttrace or is_genai):
                continue

            attributes = span.attributes or {}

            # Extract GenAI semantic conventions (fallback to empty if not found)
            system = attributes.get("gen_ai.system", "unknown")
            model = attributes.get("gen_ai.request.model", "unknown")
            input_tokens = attributes.get("gen_ai.usage.input_tokens", 0)
            output_tokens = attributes.get("gen_ai.usage.output_tokens", 0)
            total_tokens = input_tokens + output_tokens

            # Map OTel spans to our TraceStep model
            step_type = "llm_call"
            name = model if system != "unknown" else span.name

            # Handle decorator spans
            if span.attributes.get("agenttrace.type"):
                step_type = span.attributes.get("agenttrace.type")
                name = span.name.replace("agenttrace.", "")

            latency_ms = (
                int((span.end_time - span.start_time) / 1000000)
                if span.end_time and span.start_time
                else 0
            )

            # Try to extract prompts & completions (OTel GenAI conventions emit events for these)
            inputs = {"model": model, "messages": []}
            outputs = {"content": ""}

            # Check if inputs/outputs were set via attributes (like our LangChain adapter does)
            if span.attributes.get("agenttrace.inputs"):
                inputs["messages"].append(
                    {"content": span.attributes.get("agenttrace.inputs")}
                )
            if span.attributes.get("agenttrace.outputs"):
                outputs["content"] = span.attributes.get("agenttrace.outputs")

            for event in span.events:
                if event.name == "gen_ai.content.prompt":
                    inputs["messages"].append(
                        {"content": event.attributes.get("gen_ai.prompt")}
                    )
                elif event.name == "gen_ai.content.completion":
                    outputs["content"] += event.attributes.get("gen_ai.completion", "")
                elif event.name == "agenttrace.inputs":
                    inputs = json.loads(event.attributes.get("payload", "{}"))
                elif event.name == "agenttrace.outputs":
                    outputs = json.loads(event.attributes.get("payload", "{}"))

            if not inputs["messages"] and not span.attributes.get("agenttrace.type"):
                inputs["messages"] = [
                    {"content": attributes.get("gen_ai.prompt.0.content", "...")}
                ]
                outputs["content"] = attributes.get(
                    "gen_ai.completion.0.content", "..."
                )

            # For unhandled errors
            if span.events and span.events[-1].name == "exception":
                outputs = {
                    "error": span.events[-1].attributes.get(
                        "exception.message", "Unknown Error"
                    )
                }

            step = TraceStep(
                type=step_type,
                name=name,
                inputs=inputs,
                outputs=outputs,
                metrics=StepMetrics(latency_ms=latency_ms, tokens_total=total_tokens),
            )
            add_step(step)

        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

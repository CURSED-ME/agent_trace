import json

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from .models import StepMetrics, TraceStep


class AgentTraceExporter(SpanExporter):
    def export(self, spans):
        for span in spans:
            try:
                # Accept spans from any supported AI/ML provider
                is_llm_span = span.name in [
                    "chat.completions.create",
                    "chat.completions.create.stream",
                    "messages.create",  # Anthropic
                    "messages.create.stream",  # Anthropic streaming
                ]
                is_agenttrace = "agenttrace" in span.name or (
                    span.attributes and "agenttrace.type" in span.attributes
                )
                is_genai = span.attributes and any(
                    key.startswith("gen_ai.") or key.startswith("llm.")
                    for key in span.attributes.keys()
                )

                if not (is_llm_span or is_agenttrace or is_genai):
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

                # Filter out LangGraph internal orchestration chains from clogging the UI
                if step_type == "chain" and name == "langgraph.chain":
                    continue

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
                        outputs["content"] += event.attributes.get(
                            "gen_ai.completion", ""
                        )
                    elif event.name == "agenttrace.inputs":
                        inputs = json.loads(event.attributes.get("payload", "{}"))
                    elif event.name == "agenttrace.outputs":
                        outputs = json.loads(event.attributes.get("payload", "{}"))

                if not inputs["messages"] and not span.attributes.get(
                    "agenttrace.type"
                ):
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
                    metrics=StepMetrics(
                        latency_ms=latency_ms, tokens_total=total_tokens
                    ),
                )

                # Use OpenTelemetry's internal trace ID to ensure accurate grouping across threads
                otel_trace_id = format(span.get_span_context().trace_id, "032x")

                from .storage import add_step_with_trace_id

                add_step_with_trace_id(step, otel_trace_id)

                # If this is a root span ending, mark the entire trace as completed
                if span.parent is None:
                    from .storage import update_trace_status

                    update_trace_status(otel_trace_id, "completed")

            except Exception as e:
                print(f"AgentTrace Exporter Error processing span '{span.name}': {e}")
                # We do not re-raise, so we don't crash the host application or break the batch export

        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

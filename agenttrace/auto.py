import atexit
import logging
import os
import sys
import threading
import time
import traceback

from .models import StepEvaluation, StepMetrics, TraceStep
from .storage import add_step

logger = logging.getLogger("agenttrace")

_original_excepthook = sys.excepthook


def crash_handler(exc_type, exc_value, exc_traceback):
    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))

    # Add a special trace step for the crash
    add_step(
        TraceStep(
            type="server_crash",
            name="Unhandled Exception",
            inputs={
                "type": exc_type.__name__
                if hasattr(exc_type, "__name__")
                else str(exc_type),
                "value": str(exc_value),
            },
            outputs={"traceback": err_msg},
            metrics=StepMetrics(),
            evaluation=StepEvaluation(
                status="error", reasoning="Script terminated unexpectedly."
            ),
        )
    )

    # Call the original hook
    _original_excepthook(exc_type, exc_value, exc_traceback)


def _run_server():
    if (
        os.environ.get("AGENTTRACE_NO_SERVER") == "1"
        or os.environ.get("CI") == "true"
        or os.environ.get("GITHUB_ACTIONS")
    ):
        logger.info(
            "AgentTrace: Skipping dashboard server auto-launch (CI/headless environment detected)."
        )
        return

    import uvicorn

    from .server import app

    logger.info(
        "\n✨ AgentTrace: Run complete! Dashboard opened at http://localhost:8000. (Press Ctrl+C to close server and return to terminal)\n"
    )

    def open_browser():
        time.sleep(1.5)
        import webbrowser

        try:
            webbrowser.open("http://localhost:8000")
        except Exception:
            pass

    t = threading.Thread(target=open_browser)
    t.daemon = True
    t.start()

    try:
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
    except OSError:
        logger.warning(
            "AgentTrace: Dashboard is already running on port 8000 in another process."
        )
    except Exception as e:
        logger.error(f"AgentTrace: Dashboard failed to start: {e}")


def init():
    # Set up OpenTelemetry
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        from .exporter import AgentTraceExporter

        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(AgentTraceExporter()))
        trace.set_tracer_provider(provider)

        # Auto-instrument all supported AI/ML providers.
        # Each is guarded: only activates if the user has installed that provider's package.
        _instrumentors = [
            (
                "opentelemetry.instrumentation.openai",
                "OpenAIInstrumentor",
            ),  # OpenAI + Groq
            (
                "opentelemetry.instrumentation.anthropic",
                "AnthropicInstrumentor",
            ),  # Anthropic Claude
            ("opentelemetry.instrumentation.cohere", "CohereInstrumentor"),  # Cohere
            (
                "opentelemetry.instrumentation.mistralai",
                "MistralAiInstrumentor",
            ),  # Mistral AI
            (
                "opentelemetry.instrumentation.google_generativeai",
                "GoogleGenerativeAiInstrumentor",
            ),  # Google Gemini
            (
                "opentelemetry.instrumentation.bedrock",
                "BedrockInstrumentor",
            ),  # AWS Bedrock
            (
                "opentelemetry.instrumentation.replicate",
                "ReplicateInstrumentor",
            ),  # Replicate
            (
                "opentelemetry.instrumentation.together",
                "TogetherAiInstrumentor",
            ),  # Together AI
            (
                "opentelemetry.instrumentation.ollama",
                "OllamaInstrumentor",
            ),  # Ollama (local models)
            (
                "opentelemetry.instrumentation.llamaindex",
                "LlamaIndexInstrumentor",
            ),  # LlamaIndex
            (
                "opentelemetry.instrumentation.haystack",
                "HaystackInstrumentor",
            ),  # Haystack
            (
                "opentelemetry.instrumentation.chromadb",
                "ChromaInstrumentor",
            ),  # ChromaDB (vector DB)
            (
                "opentelemetry.instrumentation.pinecone",
                "PineconeInstrumentor",
            ),  # Pinecone (vector DB)
        ]

        for module_path, class_name in _instrumentors:
            try:
                module = __import__(module_path, fromlist=[class_name])
                instrumentor_cls = getattr(module, class_name)
                instrumentor_cls().instrument()
            except (ImportError, Exception):
                pass  # Provider not installed or instrumentor failed, skip silently

        # Auto-register external frameworks
        from .integrations import auto_register

        auto_register()
    except ImportError as e:
        logger.warning(
            f"AgentTrace: OTel dependencies missing ({e}). Native LLM tracing disabled."
        )

    sys.excepthook = crash_handler
    atexit.register(_run_server)


init()

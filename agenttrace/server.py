import asyncio
import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .judge import evaluate_trace
from .storage import get_trace_by_id, list_traces

logger = logging.getLogger("agenttrace")

app = FastAPI()

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.on_event("startup")
async def startup_event():
    # Clean up stale "RUNNING" traces from previous runs
    from .storage import _db_lock, _get_connection, prune_traces

    try:
        with _db_lock:
            conn = _get_connection()
            conn.execute(
                "UPDATE traces SET status = 'completed' WHERE status = 'running'"
            )
            conn.commit()

        # Enforce trace limit bounds
        prune_traces()
    except Exception as e:
        logger.warning(f"AgentTrace: Failed to clean up stale traces: {e}")

    # evaluate traces continuously in the background
    interval = int(os.environ.get("AGENTTRACE_JUDGE_INTERVAL", "5"))

    async def judge_loop():
        while True:
            try:
                await evaluate_trace()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Judge error: {e}", exc_info=True)
            await asyncio.sleep(interval)

    app.state.judge_task = asyncio.create_task(judge_loop())


@app.on_event("shutdown")
async def shutdown_event():
    if hasattr(app.state, "judge_task"):
        app.state.judge_task.cancel()
        try:
            await app.state.judge_task
        except asyncio.CancelledError:
            pass

    # Close SQLite connections on shutdown cleanly
    from .storage import _get_connection

    try:
        conn = _get_connection()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to close sqlite connection gracefully: {e}")


@app.post("/v1/traces")
async def ingest_otlp_traces(request: Request):
    from .otlp_adapter import process_span
    from .storage import add_step_with_trace_id, update_trace_status

    payload = await request.json()
    # OTLP JSON has resourceSpans -> scopeSpans -> spans
    for resource_span in payload.get("resourceSpans", []):
        for scope_span in resource_span.get("scopeSpans", []):
            for span in scope_span.get("spans", []):
                try:
                    # Map OTLP JSON Span to our otlp_adapter format
                    attributes = {}
                    for attr in span.get("attributes", []):
                        val = attr.get("value", {})
                        if "stringValue" in val:
                            attributes[attr["key"]] = val["stringValue"]
                        elif "intValue" in val:
                            attributes[attr["key"]] = int(val["intValue"])
                        elif "doubleValue" in val:
                            attributes[attr["key"]] = float(val["doubleValue"])
                        elif "boolValue" in val:
                            attributes[attr["key"]] = bool(val["boolValue"])
                        elif "arrayValue" in val:
                            arr = [
                                list(v.values())[0]
                                for v in val["arrayValue"].get("values", [])
                            ]
                            attributes[attr["key"]] = arr

                    events = []
                    for evt in span.get("events", []):
                        evt_attrs = {}
                        for attr in evt.get("attributes", []):
                            val = attr.get("value", {})
                            if "stringValue" in val:
                                evt_attrs[attr["key"]] = val["stringValue"]
                            elif "intValue" in val:
                                evt_attrs[attr["key"]] = int(val["intValue"])
                            elif "doubleValue" in val:
                                evt_attrs[attr["key"]] = float(val["doubleValue"])
                            elif "boolValue" in val:
                                evt_attrs[attr["key"]] = bool(val["boolValue"])
                        events.append(
                            {"name": evt.get("name"), "attributes": evt_attrs}
                        )

                    trace_id_hex = span.get("traceId", "")
                    span_id_hex = span.get("spanId", "")
                    parent_span_id_hex = span.get("parentSpanId")

                    step = process_span(
                        name=span.get("name", "unknown"),
                        attributes=attributes,
                        events=events,
                        start_time_unix_nano=int(span.get("startTimeUnixNano", 0)),
                        end_time_unix_nano=int(span.get("endTimeUnixNano", 0)),
                        trace_id_hex=trace_id_hex,
                        span_id_hex=span_id_hex,
                        parent_span_id_hex=parent_span_id_hex,
                    )

                    if step:
                        add_step_with_trace_id(step, trace_id_hex)
                        if not parent_span_id_hex:
                            update_trace_status(trace_id_hex, "completed")
                except Exception as e:
                    logger.warning(f"Error processing OTLP span: {e}", exc_info=True)

    return JSONResponse(
        status_code=202, content={"status": "success", "message": "Traces ingested"}
    )


@app.get("/api/traces")
def get_traces():
    traces = list_traces(limit=50)
    return JSONResponse(content={"traces": [t.model_dump(mode="json") for t in traces]})


@app.get("/api/trace/latest")
def get_latest_trace():
    traces = list_traces(limit=1)
    if traces:
        trace = get_trace_by_id(traces[0].trace_id)
        return JSONResponse(content={"trace": trace.model_dump(mode="json")})
    return JSONResponse(content={"trace": None})


@app.get("/api/trace/{trace_id}")
def get_trace(trace_id: str):
    trace = get_trace_by_id(trace_id)
    if not trace:
        return JSONResponse(status_code=404, content={"error": "Trace not found"})
    return JSONResponse(content={"trace": trace.model_dump(mode="json")})


@app.delete("/api/traces/clear")
def clear_traces():
    from .storage import clear_all_traces

    try:
        clear_all_traces()
        return JSONResponse(content={"status": "success"})
    except Exception as e:
        logger.error(f"Failed to clear traces: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# Mount static files correctly
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:

    @app.get("/")
    def no_static():
        return {
            "error": "UI not built. Run vite build and ensure static folder exists."
        }

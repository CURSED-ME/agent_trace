import asyncio
import json
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

        # Extract resource attributes for session propagation
        resource_attrs = resource_span.get("resource", {}).get("attributes", [])
        session_id = None
        tags = {}
        for attr in resource_attrs:
            key = attr.get("key", "")
            val = attr.get("value", {})
            val_str = val.get("stringValue")
            if key == "agenttrace.session_id" and val_str:
                session_id = val_str
            elif key.startswith("agenttrace.tags.") and val_str:
                k = key.replace("agenttrace.tags.", "")
                tags[k] = val_str
        opt_tags = tags if tags else None

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
                        add_step_with_trace_id(step, trace_id_hex, session_id, opt_tags)
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


@app.get("/api/sessions")
def get_sessions():
    from .storage import list_sessions
    sessions = list_sessions(limit=50)
    return JSONResponse(content={"sessions": sessions})


@app.get("/api/session/{session_id}")
def get_session(session_id: str):
    from .storage import get_session_traces
    traces = get_session_traces(session_id)
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


@app.get("/api/traces/compare")
def compare_trace_endpoint(left: str, right: str):
    from .compare import compare_traces

    left_trace = get_trace_by_id(left)
    right_trace = get_trace_by_id(right)

    if not left_trace or not right_trace:
        return JSONResponse(status_code=404, content={"error": "One or both traces not found"})

    diff = compare_traces(left_trace, right_trace)
    return JSONResponse(content=diff.model_dump(mode="json"))


@app.patch("/api/trace/{trace_id}/tags")
async def update_trace_tags(trace_id: str, request: Request):
    import json

    from .storage import _db_lock, _get_connection

    body = await request.json()
    tags = body.get("tags", {})

    with _db_lock:
        conn = _get_connection()
        conn.execute("UPDATE traces SET tags = ? WHERE trace_id = ?", (json.dumps(tags), trace_id))
        conn.commit()

    return JSONResponse(content={"status": "success"})


@app.delete("/api/traces/clear")
def clear_traces():
    from .storage import clear_all_traces

    try:
        clear_all_traces()
        return JSONResponse(content={"status": "success"})
    except Exception as e:
        logger.error(f"Failed to clear traces: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/datasets")
async def create_dataset_endpoint(request: Request):
    from .storage import create_dataset
    body = await request.json()
    name = body.get("name")
    if not name:
        return JSONResponse(status_code=400, content={"error": "Name is required"})
    description = body.get("description")
    ds = create_dataset(name, description)
    return JSONResponse(content=ds.model_dump(mode="json"))

@app.get("/api/datasets")
def list_datasets_endpoint():
    from .storage import list_datasets
    datasets = list_datasets()
    return JSONResponse(content={"datasets": [d.model_dump(mode="json") for d in datasets]})

@app.get("/api/datasets/{dataset_id}")
def get_dataset_endpoint(dataset_id: str):
    from .storage import get_dataset
    ds = get_dataset(dataset_id)
    if not ds:
        return JSONResponse(status_code=404, content={"error": "Dataset not found"})
    return JSONResponse(content=ds.model_dump(mode="json"))

@app.post("/api/datasets/{dataset_id}/items")
async def add_dataset_item_endpoint(dataset_id: str, request: Request):
    from .storage import add_dataset_item, get_dataset
    ds = get_dataset(dataset_id)
    if not ds:
        return JSONResponse(status_code=404, content={"error": "Dataset not found"})
    body = await request.json()
    item = add_dataset_item(dataset_id, body.get("inputs", {}), body.get("expected_outputs"))
    return JSONResponse(content=item.model_dump(mode="json"))

@app.get("/api/datasets/{dataset_id}/items")
def list_dataset_items_endpoint(dataset_id: str):
    from .storage import get_dataset, list_dataset_items
    ds = get_dataset(dataset_id)
    if not ds:
        return JSONResponse(status_code=404, content={"error": "Dataset not found"})
    items = list_dataset_items(dataset_id)
    return JSONResponse(content={"items": [i.model_dump(mode="json") for i in items]})

@app.get("/api/datasets/{dataset_id}/export")
def export_dataset_endpoint(dataset_id: str):
    from .storage import get_dataset, list_dataset_items
    ds = get_dataset(dataset_id)
    if not ds:
        return JSONResponse(status_code=404, content={"error": "Dataset not found"})

    items = list_dataset_items(dataset_id)
    jsonl = ""
    for idx, item in enumerate(items):
        item_dict = {
            "id": item.item_id,
            "inputs": item.inputs,
            "expected_outputs": item.expected_outputs
        }
        jsonl += json.dumps(item_dict) + "\n"

    return JSONResponse(content={"jsonl": jsonl})

@app.post("/api/datasets/{dataset_id}/batch")
async def batch_add_dataset_endpoint(dataset_id: str, request: Request):
    from .storage import (
        add_dataset_item,
        get_dataset,
        get_session_traces,
        get_trace_by_id,
        list_traces,
    )
    body = await request.json()
    source_type = body.get("source_type") # "session", "tag", "trace_ids"
    source_value = body.get("source_value")

    ds = get_dataset(dataset_id)
    if not ds:
        return JSONResponse(status_code=404, content={"error": "Dataset not found"})

    traces_to_add = []
    if source_type == "trace_ids":
        for tid in source_value:
            t = get_trace_by_id(tid)
            if t:
                traces_to_add.append(t)
    elif source_type == "session":
        traces_to_add = get_session_traces(source_value)
    elif source_type == "tag":
        if "=" in source_value:
            k, v = source_value.split("=", 1)
            all_t = list_traces(limit=1000)
            traces_to_add = [t for t in all_t if t.tags and t.tags.get(k) == v]
            # Need to fetch full traces to get steps
            traces_to_add = [get_trace_by_id(t.trace_id) for t in traces_to_add]

    added_count = 0
    for t in traces_to_add:
        if not t:
            continue
        # Find the final output step or just the first LLM call as representative
        main_steps = [s for s in t.steps if s.type == "llm_call" or s.type == "tool_execution"]
        if main_steps:
            # Just add the last step as representative of the trace outcome for now
            target_step = main_steps[-1]
            add_dataset_item(dataset_id, target_step.inputs, target_step.outputs)
            added_count += 1

    return JSONResponse(content={"status": "success", "added_count": added_count})

# Mount static files correctly
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:

    @app.get("/")
    def no_static():
        return {
            "error": "UI not built. Run vite build and ensure static folder exists."
        }

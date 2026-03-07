import os
import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from .storage import list_traces, get_trace_by_id
from .judge import evaluate_trace

app = FastAPI()

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.on_event("startup")
async def startup_event():
    # evaluate traces continuously in the background
    async def judge_loop():
        while True:
            try:
                await evaluate_trace()
            except Exception as e:
                print(f"Judge error: {e}")
            await asyncio.sleep(5)

    asyncio.create_task(judge_loop())


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


# Mount static files correctly
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:

    @app.get("/")
    def no_static():
        return {
            "error": "UI not built. Run vite build and ensure static folder exists."
        }

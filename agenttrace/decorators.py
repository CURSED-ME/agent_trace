from functools import wraps
import time
import asyncio
from .models import TraceStep, StepMetrics
from .storage import add_step


def track_tool(name=None):
    def decorator(func):
        tool_name = name or func.__name__

        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = await func(*args, **kwargs)
                    out = {"result": result}
                except Exception as e:
                    out = {"error": str(e)}
                    raise
                finally:
                    latency = int((time.time() - start) * 1000)
                    add_step(
                        TraceStep(
                            type="tool_execution",
                            name=tool_name,
                            inputs={"args": args, "kwargs": kwargs},
                            outputs=out,
                            metrics=StepMetrics(latency_ms=latency),
                        )
                    )
                return result

            return async_wrapper
        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = func(*args, **kwargs)
                    out = {"result": result}
                except Exception as e:
                    out = {"error": str(e)}
                    raise
                finally:
                    latency = int((time.time() - start) * 1000)
                    add_step(
                        TraceStep(
                            type="tool_execution",
                            name=tool_name,
                            inputs={"args": args, "kwargs": kwargs},
                            outputs=out,
                            metrics=StepMetrics(latency_ms=latency),
                        )
                    )
                return result

            return sync_wrapper

    return decorator


def track_agent(name=None):
    def decorator(func):
        agent_name = name or func.__name__

        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = await func(*args, **kwargs)
                    out = {"result": result}
                except Exception as e:
                    out = {"error": str(e)}
                    raise
                finally:
                    latency = int((time.time() - start) * 1000)
                    add_step(
                        TraceStep(
                            type="system_prompt",
                            name=agent_name,
                            inputs={"args": args, "kwargs": kwargs},
                            outputs=out,
                            metrics=StepMetrics(latency_ms=latency),
                        )
                    )
                return result

            return async_wrapper
        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = func(*args, **kwargs)
                    out = {"result": result}
                except Exception as e:
                    out = {"error": str(e)}
                    raise
                finally:
                    latency = int((time.time() - start) * 1000)
                    add_step(
                        TraceStep(
                            type="system_prompt",
                            name=agent_name,
                            inputs={"args": args, "kwargs": kwargs},
                            outputs=out,
                            metrics=StepMetrics(latency_ms=latency),
                        )
                    )
                return result

            return sync_wrapper

    return decorator

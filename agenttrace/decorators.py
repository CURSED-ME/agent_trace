import asyncio
import time
from functools import wraps

from .models import StepMetrics, TraceStep
from .storage import add_step


def track_tool(func=None, *, name=None):
    """Decorator to track tool executions. Use as @track_tool or @track_tool(name='my_tool')."""

    def decorator(f):
        tool_name = name or f.__name__

        if asyncio.iscoroutinefunction(f):

            @wraps(f)
            async def async_wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = await f(*args, **kwargs)
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

            @wraps(f)
            def sync_wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = f(*args, **kwargs)
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

    if func is not None:
        return decorator(func)
    return decorator


def track_agent(func=None, *, name=None):
    """Decorator to track agent executions. Use as @track_agent or @track_agent(name='my_agent')."""

    def decorator(f):
        agent_name = name or f.__name__

        if asyncio.iscoroutinefunction(f):

            @wraps(f)
            async def async_wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = await f(*args, **kwargs)
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

            @wraps(f)
            def sync_wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = f(*args, **kwargs)
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

    if func is not None:
        return decorator(func)
    return decorator

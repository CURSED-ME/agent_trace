# Memory: Production-Grade Test Suite

## What Was Done
Created a comprehensive production-grade test suite for AgentTrace with **41 tests** across 6 test files, all passing.

## Test Structure

| File | Tests | Category | API? |
|---|---|---|---|
| `test_decorators.py` | 11 | Decorator validation (sync/async/mixed) | No |
| `test_failure_modes.py` | 8 | Crash handler, errors, loop detection | No |
| `test_stress.py` | 8 | 50-100 step load, query perf, data integrity | No |
| `test_judge.py` | 8 | All 5 eval types (loop/cost/latency/drift/misuse) | 1 needs Groq |
| `test_react_agent.py` | 3 | ReAct loop, multi-tool, streaming | Yes (Groq) |
| `test_multi_step_chain.py` | 3 | Research pipeline, error recovery | Yes (Groq) |

## Infrastructure
- `tests/conftest.py` — `fresh_db` fixture (isolated SQLite per test), `groq_client`/`async_groq_client` fixtures
- `pytest.ini` — markers: `offline`, `integration`, `stress`

## Bug Found & Fixed
**Critical bug in `decorators.py`**: `@track_tool(name=...)` and `@track_agent(name=...)` used `func` (outer param, which is `None`) instead of `f` (inner param) in the `decorator(f)` function. This caused crashes when using custom names. Fixed by replacing all `func` → `f` references inside `decorator()`.

## Commands
```bash
# Run offline tests only (no API key)
python -m pytest tests/ -m "offline or stress" -q

# Run integration tests (needs GROQ_API_KEY)
python -m pytest tests/ -m "integration" -q

# Run everything
python -m pytest tests/ -v
```

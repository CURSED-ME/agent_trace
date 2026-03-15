import json
from typing import List, Optional

from pydantic import BaseModel

from .models import AgentTrace, TraceStep


class StepDiff(BaseModel):
    left_step: Optional[TraceStep]
    right_step: Optional[TraceStep]
    changes: List[str]  # e.g. "inputs", "outputs", "metrics.tokens_total", "evaluation.status"
    status: str  # "added", "removed", "changed", "unchanged"

class MetricsDelta(BaseModel):
    total_tokens: int
    total_latency_ms: int
    steps_count: int

class TraceDiff(BaseModel):
    left: AgentTrace
    right: AgentTrace
    steps: List[StepDiff]
    metrics_delta: MetricsDelta

def _dict_diff(d1: dict, d2: dict) -> bool:
    """True if dicts are different, False if identical."""
    # Simple JSON comparison for inputs/outputs
    return json.dumps(d1, sort_keys=True) != json.dumps(d2, sort_keys=True)

def _compare_steps(left: TraceStep, right: TraceStep) -> StepDiff:
    changes = []

    if left.name != right.name:
        changes.append("name")
    if left.type != right.type:
        changes.append("type")

    left_inputs = left.inputs if isinstance(left.inputs, dict) else (left.inputs or {})
    right_inputs = right.inputs if isinstance(right.inputs, dict) else (right.inputs or {})
    if _dict_diff(left_inputs, right_inputs):
        changes.append("inputs")

    left_outputs = left.outputs if isinstance(left.outputs, dict) else (left.outputs or {})
    right_outputs = right.outputs if isinstance(right.outputs, dict) else (right.outputs or {})
    if _dict_diff(left_outputs, right_outputs):
        changes.append("outputs")

    if left.metrics.latency_ms != right.metrics.latency_ms:
        changes.append("metrics.latency_ms")
    if left.metrics.tokens_total != right.metrics.tokens_total:
        changes.append("metrics.tokens_total")

    if left.evaluation.status != right.evaluation.status:
        changes.append("evaluation.status")
    if left.evaluation.flags != right.evaluation.flags:
        changes.append("evaluation.flags")

    status = "changed" if changes else "unchanged"

    return StepDiff(
        left_step=left,
        right_step=right,
        changes=changes,
        status=status
    )

def compare_traces(left: AgentTrace, right: AgentTrace) -> TraceDiff:
    # 1. LCS Step Matching
    # Match by (type, name)
    m = len(left.steps)
    n = len(right.steps)

    # dp[i][j] stores the length of LCS of left.steps[0..i-1] and right.steps[0..j-1]
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            ls = left.steps[i - 1]
            rs = right.steps[j - 1]
            if ls.type == rs.type and ls.name == rs.name:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    # Backtrack to find the LCS alignment
    i, j = m, n
    aligned_pairs = []
    while i > 0 and j > 0:
        ls = left.steps[i - 1]
        rs = right.steps[j - 1]
        if ls.type == rs.type and ls.name == rs.name:
            aligned_pairs.append((ls, rs))
            i -= 1
            j -= 1
        elif dp[i - 1][j] > dp[i][j - 1]:
            aligned_pairs.append((ls, None))
            i -= 1
        else:
            aligned_pairs.append((None, rs))
            j -= 1

    while i > 0:
        aligned_pairs.append((left.steps[i - 1], None))
        i -= 1
    while j > 0:
        aligned_pairs.append((None, right.steps[j - 1]))
        j -= 1

    aligned_pairs.reverse()

    # 2. Field-level diffing
    diff_steps = []
    for ls, rs in aligned_pairs:
        if ls and rs:
            diff_steps.append(_compare_steps(ls, rs))
        elif ls:
            diff_steps.append(StepDiff(left_step=ls, right_step=None, changes=["removed"], status="removed"))
        elif rs:
            diff_steps.append(StepDiff(left_step=None, right_step=rs, changes=["added"], status="added"))

    # 3. Metrics Delta
    left_tokens = sum(s.metrics.tokens_total for s in left.steps)
    right_tokens = sum(s.metrics.tokens_total for s in right.steps)

    left_latency = sum(s.metrics.latency_ms for s in left.steps)
    right_latency = sum(s.metrics.latency_ms for s in right.steps)

    metrics_delta = MetricsDelta(
        total_tokens=right_tokens - left_tokens,
        total_latency_ms=right_latency - left_latency,
        steps_count=n - m
    )

    return TraceDiff(
        left=left,
        right=right,
        steps=diff_steps,
        metrics_delta=metrics_delta
    )

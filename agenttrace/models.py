import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StepMetrics(BaseModel):
    latency_ms: int = 0
    tokens_total: int = 0


class StepEvaluation(BaseModel):
    status: str = "pending"  # pending, pass, fail
    reasoning: Optional[str] = None
    flags: List[str] = Field(default_factory=list)


class TraceStep(BaseModel):
    step_id: str = Field(default_factory=lambda: "step_" + uuid.uuid4().hex[:8])
    parent_id: Optional[str] = None  # Added for OTLP context propagation
    type: str  # llm_call, tool_execution, system_prompt
    name: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    metrics: StepMetrics = Field(default_factory=StepMetrics)
    evaluation: StepEvaluation = Field(default_factory=StepEvaluation)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentTrace(BaseModel):
    trace_id: str = Field(default_factory=lambda: "trc_" + uuid.uuid4().hex[:8])
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = "running"  # running, completed, error
    steps: List[TraceStep] = Field(default_factory=list)

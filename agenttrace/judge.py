import os
import json
import asyncio
from typing import List
from .storage import _get_connection, _db_lock, update_step, get_trace_by_id
from .models import TraceStep, AgentTrace


class JudgeEngine:
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY")

    async def evaluate_pending(self):
        # Find all trace_ids that have pending steps
        with _db_lock:
            conn = _get_connection()
            rows = conn.execute(
                "SELECT DISTINCT trace_id FROM steps WHERE json_extract(evaluation, '$.status') = 'pending'"
            ).fetchall()
            trace_ids = [r["trace_id"] for r in rows]

        for tid in trace_ids:
            trace = get_trace_by_id(tid)
            if not trace:
                continue

            # Evaluate the whole trace contextually
            await self._evaluate_trace_context(trace)

    async def _evaluate_trace_context(self, trace: AgentTrace):
        pending_steps = [s for s in trace.steps if s.evaluation.status == "pending"]
        if not pending_steps:
            return

        # Run pure python checks first
        self._check_loops(trace, pending_steps)
        self._check_cost_anomaly(trace, pending_steps)
        self._check_latency_regression(trace, pending_steps)

        # Run LLM checks if API key is present
        if self.api_key:
            try:
                import groq
            except ImportError:
                print(
                    "AgentTrace Judge: groq package not installed. Install with: pip install agenttrace[judge]"
                )
                self.api_key = None
                return

            client = groq.AsyncGroq(api_key=self.api_key)
            tasks = []
            for step in pending_steps:
                if step.type == "llm_call":
                    tasks.append(self._check_instruction_drift(client, step))
                elif step.type == "tool_execution":
                    tasks.append(self._check_tool_misuse(client, step, trace))

            if tasks:
                await asyncio.gather(*tasks)
        else:
            print("AgentTrace Judge: No GROQ_API_KEY found. Skipping LLM evaluations.")

        # Finalize pending steps
        for step in pending_steps:
            if step.evaluation.status == "pending":
                if step.evaluation.flags:
                    step.evaluation.status = "fail"
                else:
                    step.evaluation.status = "pass"

            # Save back to DB
            update_step(step)

    def _check_loops(self, trace: AgentTrace, pending_steps: List[TraceStep]):
        # Flag if the agent called the same tool 3+ times consecutively with identical arguments
        # We need to look at the sequence of steps in the trace
        tool_steps = [s for s in trace.steps if s.type == "tool_execution"]
        for p_step in pending_steps:
            if p_step.type != "tool_execution":
                continue

            # Find the index of this step in the tool_steps
            try:
                idx = tool_steps.index(p_step)
            except ValueError:
                continue

            if idx >= 2:
                prev1 = tool_steps[idx - 1]
                prev2 = tool_steps[idx - 2]

                if p_step.name == prev1.name == prev2.name and json.dumps(
                    p_step.inputs, sort_keys=True
                ) == json.dumps(prev1.inputs, sort_keys=True) == json.dumps(
                    prev2.inputs, sort_keys=True
                ):
                    if "loop_detected" not in p_step.evaluation.flags:
                        p_step.evaluation.flags.append("loop_detected")

    def _check_cost_anomaly(self, trace: AgentTrace, pending_steps: List[TraceStep]):
        # Flag if >2x average token count of previous steps (min 3 previous steps)
        llm_steps = [s for s in trace.steps if s.type == "llm_call"]
        if len(llm_steps) < 4:
            return

        for p_step in pending_steps:
            if p_step.type != "llm_call":
                continue

            try:
                idx = llm_steps.index(p_step)
            except ValueError:
                continue

            if idx >= 3:
                prev_tokens = [
                    s.metrics.tokens_total
                    for s in llm_steps[:idx]
                    if s.metrics.tokens_total > 0
                ]
                if not prev_tokens:
                    continue
                avg_tokens = sum(prev_tokens) / len(prev_tokens)
                if avg_tokens > 0 and p_step.metrics.tokens_total > avg_tokens * 2:
                    if "cost_anomaly" not in p_step.evaluation.flags:
                        p_step.evaluation.flags.append("cost_anomaly")

    def _check_latency_regression(
        self, trace: AgentTrace, pending_steps: List[TraceStep]
    ):
        # Flag if latency > 3x average of same-type steps
        for p_step in pending_steps:
            same_type_steps = [
                s
                for s in trace.steps
                if s.type == p_step.type and s.step_id != p_step.step_id
            ]
            if len(same_type_steps) >= 3:
                latencies = [
                    s.metrics.latency_ms
                    for s in same_type_steps
                    if s.metrics.latency_ms > 0
                ]
                if latencies:
                    avg_lat = sum(latencies) / len(latencies)
                    if avg_lat > 0 and p_step.metrics.latency_ms > avg_lat * 3:
                        if "latency_regression" not in p_step.evaluation.flags:
                            p_step.evaluation.flags.append("latency_regression")

    async def _check_instruction_drift(self, client, step: TraceStep):
        # Check if the LLM's response ignores instructions or hallucinates
        system_prompt = """
You are an expert AI judge evaluating a trace of an LLM agent.
Your task is to detect instruction drift, dropped context, or hallucination.
Look at the Step Input (which contains messages/context) and Step Output (the response).
Did the LLM fabricate information, or did it ignore crucial instructions/data?

Return exactly "PASS" if the step is good.
Return "FAIL: <reasoning>" if it drifts, drops context, or hallucinates.
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Step Input: {json.dumps(step.inputs)[:1000]}\nStep Output: {json.dumps(step.outputs)[:1000]}",
            },
        ]

        try:
            response = await client.chat.completions.create(
                model="llama-3.3-70b-versatile", messages=messages, temperature=0.0
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("FAIL"):
                if "instruction_drift" not in step.evaluation.flags:
                    step.evaluation.flags.append("instruction_drift")

                reasoning_split = content.split(":", 1)
                if len(reasoning_split) > 1:
                    step.evaluation.reasoning = reasoning_split[1].strip()
                else:
                    step.evaluation.reasoning = content
        except Exception as e:
            step.evaluation.flags.append("judge_error")
            step.evaluation.reasoning = str(e)

    async def _check_tool_misuse(self, client, step: TraceStep, trace: AgentTrace):
        # We check if the tool execution had an error or if args look completely wrong
        if "error" in step.outputs:
            if "tool_misuse" not in step.evaluation.flags:
                step.evaluation.flags.append("tool_misuse")
            return

        system_prompt = """
You are an expert AI judge evaluating a tool execution by an LLM agent.
Look at the Tool Name, Inputs (Args/Kwargs), and Output.
Does it look like the agent misused the tool? For example, passing missing arguments, wrong types, or misunderstanding the tool's purpose.

Return exactly "PASS" if the tool usage appears correct and valid.
Return "FAIL: <reasoning>" if the tool was misused.
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Tool: {step.name}\nInputs: {json.dumps(step.inputs)[:1000]}\nOutput: {json.dumps(step.outputs)[:1000]}",
            },
        ]

        try:
            response = await client.chat.completions.create(
                model="llama-3.3-70b-versatile", messages=messages, temperature=0.0
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("FAIL"):
                if "tool_misuse" not in step.evaluation.flags:
                    step.evaluation.flags.append("tool_misuse")
        except Exception:
            pass  # Keep it simple, don't flag judge error on secondary checks


async def evaluate_trace():
    engine = JudgeEngine()
    await engine.evaluate_pending()

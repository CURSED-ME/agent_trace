import { trace, SpanStatusCode, context } from '@opentelemetry/api';

/**
 * Wraps a function in an AgentTrace "agent" span.
 * 
 * @param name The name of the agent to track
 * @param fn The function to wrap
 * @returns The wrapped function
 */
export function trackAgent<T extends (...args: any[]) => any>(
  name: string,
  fn: T
): T {
  return trackFunction(name, "agent", fn);
}

/**
 * Wraps a function in an AgentTrace "tool" span.
 * 
 * @param name The name of the tool to track
 * @param fn The function to wrap
 * @returns The wrapped function
 */
export function trackTool<T extends (...args: any[]) => any>(
  name: string,
  fn: T
): T {
  return trackFunction(name, "tool", fn);
}

function trackFunction<T extends (...args: any[]) => any>(
  name: string,
  agentTraceType: "agent" | "tool",
  fn: T
): T {
  const tracer = trace.getTracer('agenttrace-node');

  return function(this: any, ...args: any[]): any {
    const parentContext = context.active();
    
    // Start an active span, which automatically becomes the parent of any spans created inside `fn`
    return tracer.startActiveSpan(name, {}, parentContext, (span: any) => {
      // Set properties required by AgentTrace's backend mapping logic
      span.setAttribute('agenttrace.type', agentTraceType);
      
      try {
        // Stringify arguments gracefully to avoid blowing up traces with circular JSON
        const safeInputs = JSON.stringify(args, getCircularReplacer(), 2) || "[]";
        span.setAttribute('agenttrace.inputs', safeInputs);
      } catch (e) {
        span.setAttribute('agenttrace.inputs', '["<unserializable inputs>"]');
      }

      try {
        const result = fn.apply(this, args);

        // Handle async functions
        if (result && typeof (result as any).then === 'function') {
          return (result as Promise<any>).then((resolvedResult) => {
            try {
              const safeOutputs = JSON.stringify(resolvedResult, getCircularReplacer(), 2) || "null";
              span.setAttribute('agenttrace.outputs', safeOutputs);
            } catch (e) {
              span.setAttribute('agenttrace.outputs', '"<unserializable outputs>"');
            }
            span.setStatus({ code: SpanStatusCode.OK });
            span.end();
            return resolvedResult;
          }).catch((err) => {
            recordError(span, err);
            span.end();
            throw err;
          }) as ReturnType<T>;
        }

        // Handle sync functions
        try {
          const safeOutputs = JSON.stringify(result, getCircularReplacer(), 2) || "null";
          span.setAttribute('agenttrace.outputs', safeOutputs);
        } catch (e) {
          span.setAttribute('agenttrace.outputs', '"<unserializable outputs>"');
        }
        span.setStatus({ code: SpanStatusCode.OK });
        span.end();
        return result;

      } catch (err) {
        // Handle synchronous errors
        recordError(span, err);
        span.end();
        throw err;
      }
    });
  } as T;
}

function recordError(span: any, err: any) {
  span.setStatus({
    code: SpanStatusCode.ERROR,
    message: err instanceof Error ? err.message : String(err),
  });
  span.recordException(err instanceof Error ? err : new Error(String(err)));
}

// Utility to handle JSON.stringify circular references
const getCircularReplacer = () => {
  const seen = new WeakSet();
  return (key: string, value: any) => {
    if (typeof value === "object" && value !== null) {
      if (seen.has(value)) {
        return "[Circular]";
      }
      seen.add(value);
    }
    return value;
  };
};

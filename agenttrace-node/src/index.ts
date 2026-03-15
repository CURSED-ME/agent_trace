import { NodeSDK } from '@opentelemetry/sdk-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OpenAIInstrumentation } from '@traceloop/instrumentation-openai';
import { resourceFromAttributes } from '@opentelemetry/resources';

export interface AgentTraceNodeOptions {
  apiKey?: string;
  endpoint?: string;
  serviceName?: string;
  sessionId?: string;
  tags?: Record<string, string>;
}

let sdk: NodeSDK | null = null;

export function init(options: AgentTraceNodeOptions = {}) {
  if (sdk) {
    console.warn("AgentTrace: SDK is already initialized.");
    return sdk;
  }

  const endpoint = options.endpoint || process.env.AGENTTRACE_API_URL || "http://localhost:8000/v1/traces";
  const serviceName = options.serviceName || process.env.AGENTTRACE_SERVICE_NAME || "agenttrace-node-app";

  const headers: Record<string, string> = {};
  const apiKey = options.apiKey || process.env.AGENTTRACE_API_KEY;
  if (apiKey) {
    headers["Authorization"] = `Bearer ${apiKey}`;
  }

  const exporter = new OTLPTraceExporter({
    url: endpoint,
    headers: headers,
  });

  const resAttrs: Record<string, string> = { "service.name": serviceName };

  const sessionId = options.sessionId || process.env.AGENTTRACE_SESSION_ID;
  if (sessionId) {
    resAttrs['agenttrace.session_id'] = sessionId;
  }

  const tagsToApply: Record<string, string> = { ...options.tags };
  const envTagsRaw = process.env.AGENTTRACE_TAGS;
  if (envTagsRaw) {
    envTagsRaw.split(',').forEach(pair => {
      const parts = pair.split('=');
      if (parts.length === 2) tagsToApply[parts[0].trim()] = parts[1].trim();
    });
  }

  for (const [k, v] of Object.entries(tagsToApply)) {
    resAttrs[`agenttrace.tags.${k}`] = String(v);
  }

  sdk = new NodeSDK({
    traceExporter: exporter,
    instrumentations: [
      getNodeAutoInstrumentations(),
      new OpenAIInstrumentation()
    ],
    resource: resourceFromAttributes(resAttrs),
  });

  try {
    sdk.start();
    console.log(`✨ AgentTrace initialized: exporting to ${endpoint}`);
  } catch (error) {
    console.error("AgentTrace failed to start:", error);
  }

  // Gracefully shut down the SDK on process exit
  process.on('SIGTERM', () => {
    shutdown();
  });

  return sdk;
}

export async function shutdown() {
  if (sdk) {
    try {
      await sdk.shutdown();
      console.log('AgentTrace flushed and terminated gracefully');
    } catch (e) {
      console.error('Error terminating AgentTrace', e);
    }
  }
}

export { trackAgent, trackTool } from './decorators';

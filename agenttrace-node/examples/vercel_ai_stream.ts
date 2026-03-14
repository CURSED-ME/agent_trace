import { init, shutdown } from "../dist/index.js";
import { streamText } from "ai";
import { createOpenAI } from "@ai-sdk/openai";
import * as dotenv from "dotenv";

dotenv.config({ path: "../.env" });

// 1. Initialize AgentTrace against dump server
init({
  endpoint: "http://localhost:8002/v1/traces", 
  serviceName: "vercel-ai-stream"
});

const groq = createOpenAI({
  baseURL: "https://api.groq.com/openai/v1",
  apiKey: process.env.GROQ_API_KEY || "dummy",
});

async function main() {
  console.log("Streaming text with Vercel AI...");
  const { textStream } = streamText({
    model: groq("llama-3.1-8b-instant"),
    prompt: "Count from 1 to 5 slowly.",
    experimental_telemetry: {
      isEnabled: true,
      functionId: "counter-bot",
      metadata: { agent: "counter-agent" }
    }
  });

  for await (const textPart of textStream) {
    process.stdout.write(textPart);
  }
  console.log(); // Newline
}

main()
  .catch(console.error)
  .finally(async () => {
    console.log("Shutting down SDK...");
    await shutdown();
  });

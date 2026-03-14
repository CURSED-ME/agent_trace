import { init, shutdown } from "../dist/index.js";
import { generateText } from "ai";
import { createOpenAI } from "@ai-sdk/openai";
import * as dotenv from "dotenv";

dotenv.config({ path: "../.env" });

// 1. Initialize AgentTrace
init({
  endpoint: "http://localhost:8002/v1/traces", // Point to dump server
  serviceName: "vercel-ai-bot"
});

const groq = createOpenAI({
  baseURL: "https://api.groq.com/openai/v1",
  apiKey: process.env.GROQ_API_KEY || "dummy",
});

async function main() {
  console.log("Generating text with Vercel AI SDK...");
  const { text, usage } = await generateText({
    model: groq("llama-3.1-8b-instant", { compatibility: "strict" }),
    prompt: "Write a short poem about a server.",
    experimental_telemetry: {
      isEnabled: true,
      functionId: "my-generation-function",
      metadata: {
        agent: "poet-bot"
      }
    }
  });

  console.log("Response:", text);
  console.log("Usage:", usage);
}

main()
  .catch(console.error)
  .finally(async () => {
    console.log("Shutting down SDK...");
    await shutdown();
  });

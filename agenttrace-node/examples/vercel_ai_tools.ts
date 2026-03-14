import { init, shutdown } from "../dist/index.js";
import { generateText, tool } from "ai";
import { createOpenAI } from "@ai-sdk/openai";
import { z } from "zod";
import * as dotenv from "dotenv";

dotenv.config({ path: "../.env" });

// 1. Initialize AgentTrace against dump server
init({
  endpoint: "http://localhost:8002/v1/traces", 
  serviceName: "vercel-ai-tools"
});

const groq = createOpenAI({
  baseURL: "https://api.groq.com/openai/v1",
  apiKey: process.env.GROQ_API_KEY || "dummy",
});

async function main() {
  console.log("Generating text with Vercel AI tools...");
  const { text, toolCalls, toolResults } = await generateText({
    model: groq("llama-3.3-70b-versatile"),
    prompt: "What is the weather in San Francisco?",
    tools: {
      getWeather: tool({
        description: "Get the weather for a location",
        parameters: z.object({
          location: z.string().describe("The city to get weather for"),
        }),
        execute: async ({ location }) => {
          console.log(`[Tool] Fetching weather for ${location}...`);
          await new Promise(r => setTimeout(r, 500));
          return { temperature: 72, condition: "Sunny", location };
        },
      }),
    },
    experimental_telemetry: {
      isEnabled: true,
      functionId: "weather-bot",
      metadata: { agent: "weather-agent" }
    }
  });

  console.log("Response:", text);
  console.log("Tool Calls:", toolCalls);
}

main()
  .catch(console.error)
  .finally(async () => {
    console.log("Shutting down SDK...");
    await shutdown();
  });

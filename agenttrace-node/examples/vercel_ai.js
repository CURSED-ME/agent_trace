import { init, shutdown } from "../dist/index.js";
import { generateText } from "ai";
import { openai } from "@ai-sdk/openai";
import * as dotenv from "dotenv";
import * as path from "path";
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.join(__dirname, "../../.env") });

// 1. Initialize AgentTrace
init({
  endpoint: "http://localhost:8002/v1/traces", // Point to dump server
  serviceName: "vercel-ai-bot"
});

async function main() {
  console.log("Generating text with Vercel AI SDK...");
  const { text, usage } = await generateText({
    model: openai("gpt-3.5-turbo", { compatibility: "strict" }),
    prompt: "Write a short poem about a server.",
    experimental_telemetry: {
      isEnabled: true,
      functionId: "my-generation-function"
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

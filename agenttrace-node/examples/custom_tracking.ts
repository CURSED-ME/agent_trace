import { init, shutdown, trackAgent, trackTool } from "../dist/index";
import { OpenAI } from "openai";
import * as dotenv from "dotenv";
import * as path from "path";

dotenv.config({ path: path.join(__dirname, "../../.env") });

// 1. Initialize AgentTrace
init({
  endpoint: "http://localhost:8000/v1/traces",
  serviceName: "weather-bot"
});

const client = new OpenAI({
  apiKey: process.env.GROQ_API_KEY || "dummy",
  baseURL: "https://api.groq.com/openai/v1"
});

// 2. Define a custom tool and track it
const getWeather = trackTool("getWeather", async (location: string) => {
  console.log(`[Tool] Getting weather for ${location}...`);
  // Simulate an API call latency
  await new Promise(resolve => setTimeout(resolve, 500));
  return { temp: 72, condition: "Sunny", location };
});

// 3. Define an agent that calls tools AND the LLM, and track it
const researchAgent = trackAgent("researchAgent", async (userQuery: string) => {
  console.log(`[Agent] Processing query: "${userQuery}"`);
  
  // The tool trace will automatically be nested under this agent
  const weatherData = await getWeather("San Francisco");

  console.log("[Agent] Calling LLM to summarize...");
  // The OpenAI trace will also be automatically nested under this agent!
  const response = await client.chat.completions.create({
    model: "llama-3.1-8b-instant",
    messages: [
      { role: "system", content: "You are a helpful assistant." },
      { role: "user", content: `The user asked: ${userQuery}. The weather is: ${JSON.stringify(weatherData)}. Respond.`}
    ]
  });

  return response.choices[0].message.content;
});

async function main() {
  try {
    const result = await researchAgent("Should I bring a jacket?");
    console.log("\n[Result]:", result);
  } finally {
    // 4. Always shut down to ensure traces are flushed before the Node process exits
    await shutdown();
  }
}

main().catch(console.error);

const { init } = require("../dist/index");

// Initialize AgentTrace globally
init({
  endpoint: "http://localhost:8000/v1/traces",
  serviceName: "my-node-app"
});

const { OpenAI } = require("openai");
const dotenv = require("dotenv");
const path = require("path");

dotenv.config({ path: path.join(__dirname, "../../.env") });

const client = new OpenAI({
  apiKey: process.env.GROQ_API_KEY || "dummy",
  baseURL: "https://api.groq.com/openai/v1"
});

async function main() {
  console.log("Calling OpenAI from CJS...");
  const response = await client.chat.completions.create({
    model: "llama-3.1-8b-instant",
    messages: [{ role: "user", content: "Say hello!" }],
    max_tokens: 10
  });
  
  console.log("Response:", response.choices[0].message.content);
  console.log("Shutting down AgentTrace...");
  const { shutdown } = require("../dist/index");
  await shutdown();
}

main().catch(console.error);

import { init } from '../src/index';

// Initialize AgentTrace globally
init({
  endpoint: "http://localhost:8000/v1/traces",
  serviceName: "my-node-app"
});

import * as path from 'path';
import * as dotenv from 'dotenv';
dotenv.config({ path: path.join(__dirname, '../../.env') });

async function main() {
  const { OpenAI } = await import('openai');
  const client = new OpenAI({
    apiKey: process.env.GROQ_API_KEY || "dummy",
    baseURL: "https://api.groq.com/openai/v1"
  });

  console.log("Calling OpenAI...");
  const response = await client.chat.completions.create({
    model: "llama-3.1-8b-instant",
    messages: [{ role: "user", "content": "Hello, world!" }],
    max_tokens: 20
  });
  
  console.log("Response:", response.choices[0].message.content);
  console.log("Shutting down AgentTrace...");
  await import('../src/index').then(mod => mod.shutdown());
}

main().catch(console.error);

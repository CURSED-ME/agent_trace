import os
import asyncio
from dotenv import load_dotenv

import agenttrace.auto
import groq

load_dotenv()
api_key = os.environ.get("GROQ_API_KEY")


async def main():
    client = groq.AsyncGroq(api_key=api_key)
    print("🤖 Async Agent is thinking...")

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": "What is 2 + 2? Explain in 1 sentence."}],
        stream=True,
    )

    print("\nAsync Output: ", end="")
    async for chunk in response:
        if chunk.choices[0].delta.content is not None:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print("\n")

    # Intentionally trigger an unhandled error to test Crash Detection UI
    print("Triggering intentional crash to verify Phase 4 Crash Detection...")
    raise ZeroDivisionError("OpenClaw agent attempted to divide by zero!")


if __name__ == "__main__":
    asyncio.run(main())

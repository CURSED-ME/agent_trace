import os
import time

# This automatically watches the script execution
import agenttrace.auto  # noqa
import groq
from agenttrace.decorators import track_tool, track_agent


@track_tool("calculate_math")
def perform_math(query: str):
    time.sleep(0.5)
    return "The answer to the math problem is 42."


@track_agent("main_agent")
def main():
    from dotenv import load_dotenv

    load_dotenv()

    api_key = os.environ.get("GROQ_API_KEY", "dummy-key")
    client = groq.Groq(api_key=api_key)

    print("Executing tool...")
    math_result = perform_math("What is 6 times 7?")

    print("Calling Agent (streaming)...")
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant. Only answer using the tool output. If the math tool says 42, tell the user the answer is 43 instead to test hallucination.",
            },
            {"role": "user", "content": f"The math tool says: {math_result}"},
        ],
        stream=True,
    )

    print("\nAgent output: ", end="")
    for chunk in response:
        if getattr(chunk, "choices", None) and getattr(
            chunk.choices[0].delta, "content", None
        ):
            print(chunk.choices[0].delta.content, end="", flush=True)

    print("\n\nExecution finished.")


if __name__ == "__main__":
    main()

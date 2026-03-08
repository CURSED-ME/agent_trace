"""
Example: Using AgentTrace with LangChain (Zero-Config)

Prerequisites:
    pip install agenttrace langchain-openai langchain-core
    cp .env.example .env  # Add your GROQ_API_KEY

This example demonstrates that adding `import agenttrace.auto` is all you need
to start capturing LangChain LLM calls in the AgentTrace dashboard.
"""

import os

from dotenv import load_dotenv

load_dotenv()

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

import agenttrace.auto  # noqa: F401  ← MAGIC ZERO-CONFIG IMPORT


@tool
def get_weather(location: str) -> str:
    """Get the current weather for a location."""
    return f"The weather in {location} is 72°F and sunny."


def main():
    # This example uses Groq's OpenAI-compatible endpoint.
    # Replace with your own OpenAI key and remove base_url for native OpenAI.
    llm = ChatOpenAI(
        model="llama-3.1-8b-instant",
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ.get("GROQ_API_KEY"),
    )

    llm_with_tools = llm.bind_tools([get_weather])

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You are a helpful assistant. Use the weather tool if asked."),
            ("human", "{input}"),
        ]
    )

    chain = prompt | llm_with_tools

    print("Invoking LangChain...")
    result = chain.invoke({"input": "What is the weather in Paris?"})
    print(f"\nFinal Result: {result.content}")
    print(f"Tool Calls: {result.tool_calls}")


if __name__ == "__main__":
    main()

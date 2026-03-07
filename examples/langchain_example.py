import os
from dotenv import load_dotenv

load_dotenv()

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
import agenttrace.auto  # <- MAGIC ZERO-CONFIG IMPORT

os.environ["OPENAI_API_KEY"] = os.environ.get("GROQ_API_KEY", "missing")


@tool
def get_weather(location: str) -> str:
    """Get the current weather for a location."""
    return f"The weather in {location} is 72F and sunny."


def test_langchain_agent():
    print("Initializing LangChain LLM with active AgentTrace...")

    # We use LLama3 via Groq for fast local testing since Groq mirrors OpenAI's API
    llm = ChatOpenAI(
        model="llama-3.1-8b-instant", base_url="https://api.groq.com/openai/v1"
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
    print(f"Tool Calls Triggered: {result.tool_calls}")


if __name__ == "__main__":
    test_langchain_agent()

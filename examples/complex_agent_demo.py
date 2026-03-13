import os

from dotenv import load_dotenv

load_dotenv()

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


@tool
def evaluate_math(expression: str) -> str:
    """Evaluates a mathematical expression."""
    try:
        # Safe-ish eval for demo purposes
        result = eval(expression, {"__builtins__": None}, {})
        return str(result)
    except Exception as e:
        return f"Error evaluating: {e}"


@tool
def fetch_stock_price(ticker: str) -> str:
    """Fetches the current stock price for a given ticker symbol."""
    prices = {"AAPL": "150.25", "GOOGL": "2800.50", "MSFT": "310.10"}
    return prices.get(ticker.upper(), "Ticker not found")


def main():
    llm = ChatOpenAI(
        model="llama3-70b-8192",  # Using a better model for tool calling
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ.get("GROQ_API_KEY"),
        temperature=0,
    )
    tools = [evaluate_math, fetch_stock_price]

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a highly capable financial analyst AI. Use tools to answer the user's questions.",
            ),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )

    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

    print("Running Complex Agent...")
    try:
        result = agent_executor.invoke(
            {
                "input": "If I buy 15 shares of Apple and 5 shares of Microsoft, what is my total cost?"
            }
        )
        print(f"\nFinal Result: {result['output']}")
    except Exception as e:
        print(f"\nAgent crashed: {e}")


if __name__ == "__main__":
    main()

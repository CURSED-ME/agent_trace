"""
Real-World Production Smoke Test

This script runs a genuine LangGraph ReAct Agent with real internet tools.
It includes exactly ONE line of our code: `import agenttrace.auto`.
This proves that a user can trace a complex agent with zero configuration.

Usage: python tests/e2e/realworld_research_agent.py
"""

import atexit
import os
import sys
import traceback

os.environ["PYTHONIOENCODING"] = "utf-8"

try:
    from dotenv import load_dotenv
    from langchain_community.tools import DuckDuckGoSearchRun, WikipediaQueryRun
    from langchain_community.utilities import WikipediaAPIWrapper
    from langchain_core.messages import HumanMessage
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent

    # =========================================================================
    # THE ONLY AGENTTRACE CODE:
    import agenttrace.auto

    # Unregister the dashboard server so this script can finish executing in CI
    atexit.unregister(agenttrace.auto._run_server)
    # =========================================================================

    # Load API key
    load_dotenv()
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key or api_key == "your_groq_api_key_here":
        print("❌ ERROR: GROQ_API_KEY not found in .env. Cannot run real-world test.")
        sys.exit(1)

    print("🚀 Initializing Real-World Research Agent...")

    # Initialization of LLM (using Groq's OpenAI-compatible endpoint)
    llm = ChatOpenAI(
        model="llama-3.1-8b-instant",
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key,
        temperature=0.0,
        max_retries=1,
    )

    # Tool 1: Real Internet Search (DuckDuckGo)
    search_tool = DuckDuckGoSearchRun()

    # Tool 2: Real Wikipedia Lookup
    wiki_wrapper = WikipediaAPIWrapper(top_k_results=1, doc_content_chars_max=1000)
    wiki_tool = WikipediaQueryRun(api_wrapper=wiki_wrapper)

    # Tool 3: Math Evaluator
    @tool
    def calculate(expression: str) -> str:
        """Evaluate a mathematical expression. Input must be a valid Python math string."""
        try:
            result = eval(expression, {"__builtins__": {}})
            return f"Result: {result}"
        except Exception as e:
            return f"Error evaluating '{expression}': {e}"

    # Tool 4: Report Writer
    @tool
    def write_final_report(title: str, content: str) -> str:
        """Writes the final research report to a file. Use this when you are done researching."""
        filename = "quantum_research_report.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n{content}")
        return f"Successfully saved report to {filename}"

    tools = [search_tool, wiki_tool, calculate, write_final_report]

    # Create the LangGraph ReAct agent
    print("🤖 Creating LangGraph ReAct agent...")
    agent = create_react_agent(llm, tools)

    query = (
        "Research 'Quantum Supremacy'. Use Wikipedia to understand the concept, "
        "then use DuckDuckGo to find the latest news from 2024 or 2025 about it. "
        "To show you can do math, calculate 1024 * 768 to understand how many qubits might be needed "
        "for a 2D grid of that size, and mention the result. "
        "Finally, compile a brief 2-paragraph summary and write it to a file using the tool. "
        "Do NOT stop until the file is written."
    )

    print(f"🎯 Task: {query[:80]}...\n")
    print(
        "⏳ Agent is running... This might take 10-30 seconds depending on the APIs.\n"
    )

    # Run the task autonomously
    result = agent.invoke({"messages": [HumanMessage(content=query)]})

    print("\n✅ Agent finished!")
    print("Last message from agent:")
    print(result["messages"][-1].content)
    print(
        "\nCheck the AgentTrace dashboard (http://localhost:8000) to see the full trace."
    )

except Exception as e:
    print(f"\n❌ RUNTIME CRASH: {e}")
    traceback.print_exc()
    sys.exit(1)

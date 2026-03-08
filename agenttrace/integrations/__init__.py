"""
AgentTrace Integrations Package
Auto-registers zero-config callback handlers for popular agent frameworks.
"""


def auto_register():
    import sys

    # Check for LangChain (modern usages often only import langchain_core)
    if "langchain" in sys.modules or "langchain_core" in sys.modules:
        try:
            from .langchain import register_langchain

            register_langchain()
        except Exception as e:
            print(f"AgentTrace: Failed to auto-register LangChain integration: {e}")

    # Check for CrewAI
    if "crewai" in sys.modules:
        try:
            from .crewai import register_crewai

            register_crewai()
        except Exception as e:
            print(f"AgentTrace: Failed to auto-register CrewAI integration: {e}")

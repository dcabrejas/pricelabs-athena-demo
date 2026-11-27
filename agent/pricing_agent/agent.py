"""Athena-style revenue agent: LangChain Deep Agents on DO Harness Runtime.

langgraph.json points at make_graph, an async factory, so the Action Gateway
tools can be loaded over MCP when the LangGraph server starts.

Model: DO Serverless Inference (OpenAI-compatible), a drop-in for OpenRouter.
Tools:
  - local:   get_price_recommendation, apply_price_change  (tools.py -> pricing service)
  - gateway: Action Gateway endpoint for this session (web search, the private
             listings-db MCP server, and action_code for sandboxed Python)
"""
import logging
import os
import sys
from pathlib import Path

# langgraph dev loads this file by path; make the package importable either way.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

from pricing_agent.prompt import SYSTEM_PROMPT
from pricing_agent.tools import LOCAL_TOOLS

log = logging.getLogger("pricing_agent")


def _model() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.environ["HARNESS_INFERENCE_MODEL"],
        base_url=os.environ.get("HARNESS_INFERENCE_BASE_URL", "https://inference.do-ai.run/v1"),
        api_key=os.environ["HARNESS_INFERENCE_API_KEY"],
        temperature=0,
    )


async def _gateway_tools() -> list:
    # Harness Runtime publishes the session's Action Gateway endpoint here.
    # AG_MCP_URL/AG_MCP_TOKEN are a manual fallback (e.g. running locally).
    url = os.environ.get("HARNESS_MCP_URL_DO_ACTIONS") or os.environ.get("AG_MCP_URL")
    if not url:
        log.warning("no Action Gateway endpoint in env; running with local tools only")
        return []
    conn = {"transport": "streamable_http", "url": url}
    if token := os.environ.get("AG_MCP_TOKEN"):
        conn["headers"] = {"Authorization": f"Bearer {token}"}
    tools = await MultiServerMCPClient({"do_actions": conn}).get_tools()
    log.warning("loaded %d Action Gateway tools: %s", len(tools), [t.name for t in tools])
    return tools


async def make_graph():
    return create_deep_agent(
        model=_model(),
        tools=[*LOCAL_TOOLS, *await _gateway_tools()],
        middleware=[TodoListMiddleware()],
        system_prompt=SYSTEM_PROMPT,
        name="athena-demo",
    )

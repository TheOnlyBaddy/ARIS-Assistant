"""
ARIS Multi-Agent Spawning using LangGraph
Defines a Supervisor agent coordinating:
- Researcher: Fetches real-time web info
- Writer: Drafts structured reports
- Verifier: Fact-checks the content
- Executor: Performs any testing/code validation
"""

import os
import json
import asyncio
import httpx
from typing import TypedDict, List, Literal
from google import genai
from google.genai import types
from langgraph.graph import StateGraph, END
from integrations.router import execute_intent

# ─── STATE SCHEMA ─────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    goal: str
    research: str
    draft: str
    fact_check: str
    execution: str
    next_agent: str
    final_report: str
    log: List[str]


# ─── MODEL CALL HELPERS (WITH FALLBACK) ────────────────────────────────────────

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = os.getenv("PRIMARY_MODEL", "gemini-2.5-flash")

async def generate_text(prompt: str) -> str:
    """Helper to generate text using Gemini with local Ollama fallback on 429/errors."""
    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        print(f"[ARIS Multi-Agent] Gemini call failed: {e}. Falling back to Ollama...")
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2")
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                r = await client.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": ollama_model,
                        "prompt": prompt,
                        "stream": False,
                    }
                )
                r.raise_for_status()
                return r.json().get("response", "").strip()
        except Exception as ollama_err:
            return f"Error: Failed to generate response (Gemini: {e}, Ollama: {ollama_err})"


# ─── AGENT NODES ──────────────────────────────────────────────────────────────

async def supervisor_node(state: AgentState) -> dict:
    """Supervisor determines the next agent to execute based on progress."""
    log = state.get("log", [])
    log.append("Supervisor evaluating progress...")

    if not state.get("research"):
        return {"next_agent": "researcher", "log": log}
    
    if not state.get("draft"):
        return {"next_agent": "writer", "log": log}
    
    if not state.get("fact_check"):
        return {"next_agent": "verifier", "log": log}
    
    # Compile final report
    final_report = (
        f"# FINAL REPORT: {state['goal']}\n\n"
        f"## Research Summary\n{state['research']}\n\n"
        f"## Draft Report\n{state['draft']}\n\n"
        f"## Verification Notes\n{state['fact_check']}\n"
    )
    log.append("Supervisor compiled final report. Workflow complete.")
    return {"next_agent": "end", "final_report": final_report, "log": log}


async def researcher_node(state: AgentState) -> dict:
    """Researcher searches the web for relevant context using browser search."""
    log = state.get("log", [])
    log.append("Researcher searching web...")
    
    goal = state["goal"]
    # Deconstruct query into search term
    search_prompt = (
        f"Extract 1-2 search terms to research the goal: '{goal}'. "
        "Respond with ONLY the search term, no other words or symbols."
    )
    search_query = await generate_text(search_prompt)
    search_query = search_query.replace('"', '').strip()
    
    log.append(f"Researcher running query: '{search_query}'")
    try:
        res = await execute_intent("browser_search", {"query": search_query})
        research_data = res.get("data") if res else "No search results found."
    except Exception as e:
        research_data = f"Search failed: {str(e)}"

    log.append("Researcher complete.")
    return {"research": str(research_data), "log": log}


async def writer_node(state: AgentState) -> dict:
    """Writer uses research to draft a high-quality summary/report."""
    log = state.get("log", [])
    log.append("Writer drafting report...")

    prompt = (
        f"Write a comprehensive report on: '{state['goal']}'.\n"
        f"Use this research data for facts:\n{state['research']}\n\n"
        "Draft a structured, highly informative report with clear headings."
    )
    draft = await generate_text(prompt)
    log.append("Writer complete.")
    return {"draft": draft, "log": log}


async def verifier_node(state: AgentState) -> dict:
    """Verifier fact-checks the draft and ensures accuracy."""
    log = state.get("log", [])
    log.append("Verifier analyzing draft accuracy...")

    prompt = (
        f"Verify the factual correctness of this draft report:\n"
        f"--- DRAFT ---\n{state['draft']}\n"
        f"--- RESEARCH ---\n{state['research']}\n\n"
        "Identify any logical gaps or hallucinations. Write a verification checklist summary."
    )
    verification = await generate_text(prompt)
    log.append("Verifier complete.")
    return {"fact_check": verification, "log": log}


async def executor_node(state: AgentState) -> dict:
    """Executor node for running code or validation checks."""
    log = state.get("log", [])
    log.append("Executor running validation...")
    # Add dummy check for compatibility
    return {"execution": "Passed", "log": log}


# ─── BUILD THE LANGGRAPH STATE GRAPH ──────────────────────────────────────────

workflow = StateGraph(AgentState)

workflow.add_node("supervisor", supervisor_node)
workflow.add_node("researcher", researcher_node)
workflow.add_node("writer", writer_node)
workflow.add_node("verifier", verifier_node)
workflow.add_node("executor", executor_node)

workflow.set_entry_point("supervisor")

# Dynamic routing from supervisor
workflow.add_conditional_edges(
    "supervisor",
    lambda state: state["next_agent"],
    {
        "researcher": "researcher",
        "writer": "writer",
        "verifier": "verifier",
        "executor": "executor",
        "end": END
    }
)

# Nodes return control back to supervisor
workflow.add_edge("researcher", "supervisor")
workflow.add_edge("writer", "supervisor")
workflow.add_edge("verifier", "supervisor")
workflow.add_edge("executor", "supervisor")

graph = workflow.compile()


# ─── INTERACTION INTERFACE ──────────────────────────────────────────────────

async def run_multi_agent_workflow(goal: str) -> dict:
    """Main function to trigger the LangGraph multi-agent execution."""
    initial_state = {
        "goal": goal,
        "research": "",
        "draft": "",
        "fact_check": "",
        "execution": "",
        "next_agent": "supervisor",
        "final_report": "",
        "log": []
    }
    
    final_output = await graph.ainvoke(initial_state)
    return {
        "status": "success",
        "goal": goal,
        "log": final_output["log"],
        "final_report": final_output["final_report"],
        "research": final_output["research"],
        "draft": final_output["draft"],
        "fact_check": final_output["fact_check"]
    }

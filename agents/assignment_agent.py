"""
Assignment Agent -- Central coordinator and the 'face' of the chat.

Every user message flows through here. The agent uses OpenAI to:
1. Understand intent (conversational, so it handles follow-ups too)
2. Reply in natural language
3. Decide whether to delegate to a specialist agent
4. Extract parameters the specialist needs
"""

import json
import logging
from datetime import datetime

from openai import OpenAI
from config import Config

logger = logging.getLogger(__name__)

client = OpenAI(api_key=Config.OPENAI_API_KEY, timeout=60.0)

# ── Intent categories ──────────────────────────────────────────────────────
INTENTS = {
    "expense_recording": {
        "agent": "Accounting Agent",
        "description": "Record expenses / charge entries, process CSV expense files, create orders on qualityb2bpackage.com",
    },
    "data_analysis": {
        "agent": "Data Analysis Agent",
        "description": "Retrieve booking data, sales reports, seller performance from the website",
    },
    "market_analysis": {
        "agent": "Market Analysis Agent",
        "description": "Analyse travel packages, competitive pricing, market trends, itinerary comparison",
    },
    "executive_report": {
        "agent": "Executive Agent",
        "description": "Generate executive summaries, aggregate reports, strategic insights",
    },
    "admin_task": {
        "agent": "Admin Agent",
        "description": "List / search existing records, system maintenance, lookups on the website",
    },
    "general": {
        "agent": "Assignment Agent",
        "description": "Greetings, help, status checks, general questions about the system",
    },
}

CATEGORIES_BLOCK = "\n".join(
    f"- {key}: {info['description']}" for key, info in INTENTS.items()
)

SYSTEM_PROMPT = f"""You are the **Assignment Agent** for Web365 ClawBot -- the central coordinator for a multi-agent system that manages Quality B2B Package travel operations at qualityb2bpackage.com.

## Your responsibilities
1. Greet the user warmly and answer questions conversationally.
2. Classify every request into ONE of these intents:
{CATEGORIES_BLOCK}
3. When delegation is needed, extract the parameters the specialist agent requires.
4. If the user's request is vague, ask a short clarifying question (intent = "general").

## Specialist capabilities (so you can tell the user what's possible)
- **Accounting Agent** -- Upload a CSV / Excel / PDF file with tour codes and amounts. The system logs in to qualityb2bpackage.com, fills the charges form, submits, and returns order numbers.
- **Data Analysis Agent** -- Scrapes the /booking and /report/report_seller pages and returns structured data.
- **Market Analysis Agent** -- Scrapes /travelpackage, analyses the product catalogue, produces competitive insights. Can also parse uploaded itinerary PDFs and compare them.
- **Executive Agent** -- Aggregates outputs from all other agents into a strategic report with recommendations.
- **Admin Agent** -- Lists existing expense records, bookings, or performs lookups on the website.

## Response format
Always reply with **valid JSON** (nothing else):
{{{{
  "intent": "<one of the intent keys above>",
  "confidence": <0.0-1.0>,
  "response": "<your natural language reply -- markdown is fine>",
  "delegate": true | false,
  "task_details": {{{{
    "action": "<what the specialist should do>",
    "parameters": {{{{ ... }}}}
  }}}}
}}}}

Set `delegate` to **false** when you can answer directly (greetings, help, clarifications).
Set `delegate` to **true** when a specialist agent should take over.
"""


def process_message(
    message: str,
    file_path: str = None,
    history: list = None,
) -> dict:
    """
    Classify the user's message and produce a response + delegation decision.

    Returns dict with keys: intent, response, delegate, agent, task_details
    """
    # Build conversation messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Include recent history for context (last 6 turns max)
    if history:
        for turn in history[-6:]:
            messages.append({
                "role": turn.get("role", "user"),
                "content": turn.get("content", ""),
            })

    # Current user message
    user_content = message or ""
    if file_path:
        user_content += f"\n\n[The user has uploaded a file: {file_path}]"
    messages.append({"role": "user", "content": user_content})

    try:
        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        logger.info(
            "Assignment Agent -> intent=%s  delegate=%s  confidence=%.2f",
            result.get("intent"),
            result.get("delegate"),
            result.get("confidence", 0),
        )
        return result

    except Exception as e:
        logger.error(f"Assignment Agent LLM call failed: {e}", exc_info=True)
        return {
            "intent": "general",
            "confidence": 0,
            "response": f"Sorry, I'm having trouble processing your request. ({e})",
            "delegate": False,
            "task_details": {},
        }


def delegate(intent: str, task_details: dict, file_path: str, emit_fn) -> dict | None:
    """
    Hand off to the appropriate specialist agent.

    Returns {"content": "...", "data": ...} or None.
    """
    info = INTENTS.get(intent, INTENTS["general"])
    agent_name = info["agent"]

    if intent == "general":
        return None  # nothing to delegate

    # Show the specialist as active
    if emit_fn:
        emit_fn("agent_status", {
            "agent": agent_name,
            "status": "working",
            "message": f"Working on: {task_details.get('action', 'task')}",
        })

    result = None
    try:
        if intent == "expense_recording":
            if file_path:
                from services.expense_service import start_expense_job
                result = start_expense_job(file_path=file_path, emit_fn=emit_fn)
            else:
                from agents.accounting_agent import handle_expense_task
                result = handle_expense_task(task_details, file_path, emit_fn)

        elif intent == "data_analysis":
            from agents.data_analysis_agent import handle_data_analysis_task
            result = handle_data_analysis_task(task_details, emit_fn)

        elif intent == "market_analysis":
            from agents.market_analysis_agent import handle_market_analysis_task
            result = handle_market_analysis_task(task_details, emit_fn)

        elif intent == "executive_report":
            from agents.executive_agent import handle_executive_task
            result = handle_executive_task(task_details, emit_fn)

        elif intent == "admin_task":
            from agents.admin_agent import handle_admin_task
            result = handle_admin_task(task_details, emit_fn)

    except Exception as e:
        logger.error(f"{agent_name} failed: {e}", exc_info=True)
        result = {"content": f"The {agent_name} encountered an error: {str(e)}"}

    finally:
        if emit_fn:
            emit_fn("agent_status", {
                "agent": agent_name,
                "status": "idle",
                "message": "Idle",
            })

    return result

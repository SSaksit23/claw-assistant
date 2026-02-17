"""
Assignment Agent -- Central coordinator that receives user requests,
classifies intent, and delegates to specialized agents.
"""

import json
import logging
from datetime import datetime

from openai import OpenAI

from config import Config

logger = logging.getLogger(__name__)

client = OpenAI(api_key=Config.OPENAI_API_KEY)

# Intent categories that map to specialized agents
INTENT_CATEGORIES = {
    "expense_recording": {
        "agent": "Accounting Agent",
        "description": "Record expenses, create charge entries, process CSV expense files",
    },
    "data_analysis": {
        "agent": "Data Analysis Agent",
        "description": "Retrieve booking data, sales reports, seller performance",
    },
    "market_analysis": {
        "agent": "Market Analysis Agent",
        "description": "Analyze travel packages, competitive pricing, market trends",
    },
    "executive_report": {
        "agent": "Executive Agent",
        "description": "Generate executive summaries, aggregate reports, strategic insights",
    },
    "admin_task": {
        "agent": "Admin Agent",
        "description": "Administrative record management, data entry, system maintenance",
    },
    "general_query": {
        "agent": "Assignment Agent",
        "description": "General questions, help, status checks, greetings",
    },
}

SYSTEM_PROMPT = """You are the Assignment Agent for the Web365 ClawBot system -- a multi-agent platform for managing Quality B2B Package travel operations.

Your job is to:
1. Understand the user's request
2. Classify it into one of these intent categories: {categories}
3. Generate a helpful response
4. If the request requires a specialized agent, prepare the task delegation

Always respond in valid JSON with this structure:
{{
    "intent": "<intent_category>",
    "confidence": <0.0 to 1.0>,
    "response": "<your natural language response to the user>",
    "task_details": {{
        "action": "<specific action to perform>",
        "parameters": {{<any extracted parameters>}}
    }}
}}

Context about the system:
- Expense Recording: automates filling expense forms on qualityb2bpackage.com from CSV data
- Data Analysis: scrapes booking data and seller reports from the website
- Market Analysis: analyzes travel packages and competitive landscape
- Executive Reports: aggregates all data into strategic business reports
- Admin Tasks: general administrative record management on the website

Be concise and helpful. If the user provides a file (CSV), assume they want expense processing unless stated otherwise."""

CATEGORIES_STR = "\n".join(
    f"- {k}: {v['description']}" for k, v in INTENT_CATEGORIES.items()
)


def classify_intent(message: str, file_path: str = None) -> dict:
    """Use OpenAI to classify user intent and generate a response."""
    user_content = message
    if file_path:
        user_content += f"\n\n[User has uploaded a file: {file_path}]"

    try:
        response = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT.format(categories=CATEGORIES_STR),
                },
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        logger.info(f"Intent classified: {result.get('intent')} (confidence: {result.get('confidence')})")
        return result

    except Exception as e:
        logger.error(f"Intent classification failed: {e}", exc_info=True)
        return {
            "intent": "general_query",
            "confidence": 0.0,
            "response": f"I'm having trouble understanding your request right now. Error: {str(e)}",
            "task_details": {},
        }


def _delegate_to_agent(intent: str, task_details: dict, file_path: str, emit_fn):
    """Delegate the task to the appropriate specialized agent."""
    agent_info = INTENT_CATEGORIES.get(intent, INTENT_CATEGORIES["general_query"])
    agent_name = agent_info["agent"]

    # Notify UI which agent is working
    if emit_fn:
        emit_fn("agent_status", {
            "agent": agent_name,
            "status": "working",
            "message": f"Processing: {task_details.get('action', 'task')}",
        })

    result = None

    try:
        if intent == "expense_recording":
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
        logger.error(f"Agent {agent_name} failed: {e}", exc_info=True)
        result = {"content": f"The {agent_name} encountered an error: {str(e)}"}

    finally:
        if emit_fn:
            emit_fn("agent_status", {
                "agent": agent_name,
                "status": "idle",
                "message": "Idle",
            })

    return result


def process_user_request(
    message: str,
    file_path: str = None,
    session_id: str = None,
    emit_fn=None,
) -> dict:
    """
    Main entry point: classify user intent and route to the right agent.

    Returns a dict with 'content', 'agent', and optionally 'data'.
    """
    logger.info(f"Processing request (session={session_id}): {message[:100]}")

    # Step 1: Classify intent
    classification = classify_intent(message, file_path)
    intent = classification.get("intent", "general_query")
    response_text = classification.get("response", "")
    task_details = classification.get("task_details", {})

    # Step 2: For general queries, just return the LLM response
    if intent == "general_query":
        return {
            "content": response_text,
            "agent": "Assignment Agent",
            "data": None,
        }

    # Step 3: Notify the user about delegation
    agent_info = INTENT_CATEGORIES.get(intent, {})
    agent_name = agent_info.get("agent", "Unknown Agent")

    if emit_fn:
        emit_fn("agent_progress", {
            "agent": "Assignment Agent",
            "message": f"Routing your request to **{agent_name}**...",
        })

    # Step 4: Delegate to specialized agent
    agent_result = _delegate_to_agent(intent, task_details, file_path, emit_fn)

    if agent_result and agent_result.get("content"):
        # Combine assignment agent intro with specialized agent response
        combined = f"{response_text}\n\n---\n\n{agent_result['content']}"
        return {
            "content": combined,
            "agent": agent_name,
            "data": agent_result.get("data"),
        }

    # If specialized agent had no output, return the assignment agent's response
    return {
        "content": response_text,
        "agent": "Assignment Agent",
        "data": None,
    }

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
from services import learning_service

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
- **Accounting Agent** -- Two modes:
  1. **File upload**: Upload a CSV / Excel / PDF / DOCX file with expense data. The system parses
     the document, logs in to qualityb2bpackage.com, fills the charges form, submits, and returns
     order numbers.
  2. **Manual entry**: Type the expense details directly in chat (no file needed). The system
     extracts the fields from your message and runs the same automation pipeline.
- **Data Analysis Agent** -- Scrapes the /booking and /report/report_seller pages and returns structured data.
- **Market Analysis Agent** -- Scrapes /travelpackage, analyses the product catalogue, produces competitive insights. Can also parse uploaded itinerary PDFs and compare them.
- **Executive Agent** -- Aggregates outputs from all other agents into a strategic report with recommendations.
- **Admin Agent** -- Lists existing expense records, bookings, or performs lookups on the website.

## Parameter extraction for expense_recording
When the intent is `expense_recording`, extract ALL available fields from the user's message:

**Required** (ask if missing):
- **company_name**: Which company this expense belongs to (e.g., "Go365Travel", "2U Center",
  "GO HOLIDAY TOUR"). Look for phrases like "for Go365Travel", "expense of 2U Center",
  "ของบริษัท Go365", etc.
  If the user does NOT specify the company name, set company_name to "" and ask them
  "Which company should this expense be created for?" in your response. Set delegate to false
  until they answer.

**For manual entry (no file uploaded)**, also extract these if mentioned:
- **tour_code**: Group/tour code (e.g., "BTNRTXJ260313W02", "2UCKG3NCKG3U260310B")
- **program_code**: Program code if different from tour code (e.g., "BT-NRT_W02_XJ")
- **supplier_name**: Supplier / pay-to company name
- **amount**: Total amount (calculate from unit_price x pax if not given directly)
- **unit_price**: Price per person/unit
- **pax**: Number of passengers / quantity
- **currency**: THB, CNY, USD, etc. (default THB if not specified)
- **charge_type**: One of: flight, land_tour, single_supplement, service_fee, guide_tip, visa,
  accommodation, meal, transport, insurance, entrance_fee, commission, other
- **expense_label**: English label (e.g., "Airline Ticket", "Tour Fare", "Service Fee")
- **travel_date**: Travel date range (e.g., "13-18 Mar 2026")
- **description**: Free-text description / remark

If the user provides a tour_code (with or without a file), set delegate to true.
If no file AND no tour_code, ask: "Please provide the tour/group code for this expense."

## Response format
Always reply with **valid JSON** (nothing else):
{{{{
  "intent": "<one of the intent keys above>",
  "confidence": <0.0-1.0>,
  "response": "<your natural language reply -- markdown is fine>",
  "delegate": true | false,
  "task_details": {{{{
    "action": "<what the specialist should do>",
    "parameters": {{{{ "company_name": "<extracted or empty string>", ... }}}}
  }}}}
}}}}

Set `delegate` to **false** when you can answer directly (greetings, help, clarifications).
Set `delegate` to **true** when a specialist agent should take over.
For expense_recording: set delegate to **false** if company_name is missing -- ask the user first.
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

    # Consult past learnings for relevant context
    past_learnings = learning_service.get_relevant_learnings(
        task_description=user_content,
        agent="Assignment Agent",
        limit=3,
    )
    if past_learnings:
        user_content += f"\n\n[SYSTEM - Past learnings to consider:\n{past_learnings}]"

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
        learning_service.log_error(
            agent="Assignment Agent",
            error_type="llm_call_failed",
            summary="OpenAI API call failed during intent classification",
            error_message=str(e),
            context=f"User message: {message[:200]}",
            related_files=["agents/assignment_agent.py"],
        )
        return {
            "intent": "general",
            "confidence": 0,
            "response": f"Sorry, I'm having trouble processing your request. ({e})",
            "delegate": False,
            "task_details": {},
        }


def delegate(
    intent: str, task_details: dict, file_path: str, emit_fn,
    session_id: str = "default",
    website_username: str = None,
    website_password: str = None,
    expense_type: str = "",
) -> dict | None:
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
            params = task_details.get("parameters", {})
            company = params.get("company_name", "")
            if file_path:
                from services.expense_service import review_expense_invoice
                result = review_expense_invoice(
                    file_path=file_path,
                    emit_fn=emit_fn,
                    session_id=session_id,
                    company_name=company,
                    expense_type=expense_type,
                )
            elif params.get("tour_code"):
                from services.expense_service import start_manual_expense_job
                result = start_manual_expense_job(
                    params=params,
                    emit_fn=emit_fn,
                    session_id=session_id,
                    website_username=website_username,
                    website_password=website_password,
                    company_name=company,
                    expense_type=expense_type,
                )
            else:
                result = {
                    "content": (
                        "I need more details to create an expense. Please provide:\n"
                        "1. **Tour/group code** (e.g., `BTNRTXJ260313W02`)\n"
                        "2. **Amount** or unit price x pax\n"
                        "3. **Company name** (e.g., Go365Travel)\n\n"
                        "Or upload a file (CSV / Excel / PDF / DOCX) with the expense data."
                    ),
                }

        elif intent == "data_analysis":
            from agents.data_analysis_agent import handle_data_analysis_task
            result = handle_data_analysis_task(
                task_details, emit_fn,
                session_id=session_id,
                website_username=website_username,
                website_password=website_password,
            )

        elif intent == "market_analysis":
            from agents.market_analysis_agent import handle_market_analysis_task
            result = handle_market_analysis_task(
                task_details, emit_fn,
                session_id=session_id,
                website_username=website_username,
                website_password=website_password,
            )

        elif intent == "executive_report":
            from agents.executive_agent import handle_executive_task
            result = handle_executive_task(task_details, emit_fn)

        elif intent == "admin_task":
            from agents.admin_agent import handle_admin_task
            result = handle_admin_task(
                task_details, emit_fn,
                session_id=session_id,
                website_username=website_username,
                website_password=website_password,
            )

    except Exception as e:
        logger.error(f"{agent_name} failed: {e}", exc_info=True)
        learning_service.log_error(
            agent=agent_name,
            error_type="delegation_failed",
            summary=f"{agent_name} failed during task execution",
            error_message=str(e),
            context=f"Intent: {intent}, Action: {task_details.get('action', 'N/A')}",
            related_files=[f"agents/{intent}_agent.py"],
        )
        result = {"content": f"The {agent_name} encountered an error: {str(e)}"}

    finally:
        if emit_fn:
            emit_fn("agent_status", {
                "agent": agent_name,
                "status": "idle",
                "message": "Idle",
            })

    return result

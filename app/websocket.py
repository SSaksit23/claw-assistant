"""
WebSocket event handlers for real-time chat communication.

Routes user messages and file uploads to the expense service.
No LLM needed for routing -- we use simple keyword matching and
file presence to decide the workflow.
"""

import logging
import uuid
from datetime import datetime

from flask_socketio import emit
from flask import request

from app import socketio

logger = logging.getLogger(__name__)

# In-memory session store
sessions = {}


@socketio.on("connect")
def handle_connect():
    """Handle new WebSocket connection."""
    sid = request.sid
    sessions[sid] = {
        "id": sid,
        "connected_at": datetime.utcnow().isoformat(),
        "messages": [],
    }
    logger.info(f"Client connected: {sid}")
    emit("system_message", {
        "type": "system",
        "content": "Connected to Web365 ClawBot. Upload a file or type a command to get started.",
        "timestamp": datetime.utcnow().isoformat(),
    })


@socketio.on("disconnect")
def handle_disconnect():
    """Handle WebSocket disconnection."""
    sid = request.sid
    sessions.pop(sid, None)
    logger.info(f"Client disconnected: {sid}")


@socketio.on("user_message")
def handle_user_message(data):
    """
    Process incoming user message.

    Routing logic (no LLM needed):
    - If file_path is provided -> expense processing workflow
    - If message contains expense keywords -> expense help
    - Otherwise -> general help / status check
    """
    sid = request.sid
    message = data.get("message", "").strip()
    file_path = data.get("file_path")

    if not message and not file_path:
        emit("agent_response", {
            "type": "error",
            "content": "Please enter a message or upload a file.",
            "timestamp": datetime.utcnow().isoformat(),
        })
        return

    logger.info(f"User message from {sid}: {message[:100]} (file: {file_path})")

    # Store message
    if sid in sessions:
        sessions[sid]["messages"].append({
            "role": "user",
            "content": message,
            "file_path": file_path,
            "timestamp": datetime.utcnow().isoformat(),
        })

    try:
        # ── Route 1: File uploaded -> Expense processing ──
        if file_path:
            _handle_expense_upload(file_path, message, emit)
            return

        # ── Route 2: Keyword-based routing ──
        msg_lower = message.lower()

        if any(kw in msg_lower for kw in ["expense", "charge", "upload", "csv", "ยอดเบิก", "ค่าใช้จ่าย"]):
            emit("agent_response", {
                "type": "response",
                "content": (
                    "To record expenses, please **upload a file** (CSV, Excel, PDF, or DOCX) "
                    "containing your expense data.\n\n"
                    "**Expected fields:**\n"
                    "- Tour/group code\n"
                    "- Travel date\n"
                    "- Number of passengers (size)\n"
                    "- Amount/price\n\n"
                    "You can also use the **REST API** directly:\n"
                    "```\nPOST /api/expenses\n{\"tour_code\": \"JAPAN7N-001\", \"amount\": 5000}\n```"
                ),
                "agent": "ClawBot",
                "timestamp": datetime.utcnow().isoformat(),
            })
            return

        if any(kw in msg_lower for kw in ["status", "job", "result"]):
            _handle_status_check(message, emit)
            return

        if any(kw in msg_lower for kw in ["analyze itinerary", "วิเคราะห์", "itinerary", "compare tour"]):
            _handle_itinerary_command(message, data.get("file_path"), emit)
            return

        if any(kw in msg_lower for kw in ["market intelligence", "market analysis", "วิเคราะห์ตลาด"]):
            _handle_market_intelligence(message, data.get("file_path"), emit)
            return

        if any(kw in msg_lower for kw in ["package", "travel", "tour", "โปรแกรม", "ทัวร์"]):
            emit("agent_response", {
                "type": "response",
                "content": (
                    "To extract travel packages, use the API:\n"
                    "```\nGET /api/packages?keyword=japan&limit=20\n```\n\n"
                    "Or configure an **n8n workflow** to pull package data automatically.\n\n"
                    "**New:** You can also analyse itinerary PDFs:\n"
                    "- Upload a PDF and say `analyze itinerary`\n"
                    "- Upload 2+ PDFs and say `compare tour`\n"
                    "- Say `market intelligence` to run a full market analysis"
                ),
                "agent": "ClawBot",
                "timestamp": datetime.utcnow().isoformat(),
            })
            return

        if any(kw in msg_lower for kw in ["help", "สวัสดี", "hello", "hi"]):
            _send_help(emit)
            return

        # ── Route 3: Default help ──
        _send_help(emit)

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        emit("agent_response", {
            "type": "error",
            "content": f"An error occurred: {str(e)}",
            "timestamp": datetime.utcnow().isoformat(),
        })


def _handle_expense_upload(file_path: str, message: str, emit_fn):
    """Handle an uploaded file for expense processing."""
    emit_fn("agent_status", {
        "agent": "Assignment Agent",
        "status": "working",
        "message": "Processing uploaded file...",
    })

    try:
        from services.expense_service import start_expense_job
        result = start_expense_job(file_path=file_path, emit_fn=emit_fn)

        emit_fn("agent_response", {
            "type": "response",
            "content": result.get("content", "Processing complete."),
            "agent": result.get("agent", "ClawBot"),
            "data": result.get("data"),
            "timestamp": datetime.utcnow().isoformat(),
        })

    except Exception as e:
        logger.error(f"Expense processing failed: {e}", exc_info=True)
        emit_fn("agent_response", {
            "type": "error",
            "content": f"Expense processing failed: {str(e)}",
            "timestamp": datetime.utcnow().isoformat(),
        })

    finally:
        emit_fn("agent_status", {
            "agent": "Assignment Agent",
            "status": "idle",
            "message": "Ready",
        })


def _handle_status_check(message: str, emit_fn):
    """Check job status."""
    # Try to extract job ID from message
    import re
    match = re.search(r"[a-f0-9]{8}", message)
    if match:
        job_id = match.group()
        from services.expense_service import get_job
        job = get_job(job_id)
        if job:
            emit_fn("agent_response", {
                "type": "response",
                "content": (
                    f"**Job `{job_id}`**\n"
                    f"- Status: {job['status']}\n"
                    f"- Started: {job.get('started_at', 'N/A')}\n"
                    f"- Steps completed: {len(job.get('steps', []))}\n"
                    f"- Results: {len(job.get('results', []))} records"
                ),
                "agent": "ClawBot",
                "timestamp": datetime.utcnow().isoformat(),
            })
            return

    emit_fn("agent_response", {
        "type": "response",
        "content": "No active jobs found. Upload a file to start processing.",
        "agent": "ClawBot",
        "timestamp": datetime.utcnow().isoformat(),
    })


def _handle_itinerary_command(message: str, file_path: str, emit_fn):
    """Handle itinerary analysis commands."""
    emit_fn("agent_status", {
        "agent": "Analysis Agent",
        "status": "working",
        "message": "Analysing itinerary...",
    })

    try:
        if file_path:
            from tools.itinerary_tools import analyze_itinerary_tool
            result = analyze_itinerary_tool(file_path, language="auto", save_output=True)

            if result.get("status") == "success":
                data = result["data"]
                summary = (
                    f"## Itinerary Analysis Complete\n\n"
                    f"**Tour:** {data.get('tourName', 'N/A')}\n"
                    f"**Duration:** {data.get('duration', 'N/A')}\n"
                    f"**Destinations:** {', '.join(data.get('destinations', []))}\n\n"
                )

                if data.get("pricing"):
                    summary += "### Pricing\n"
                    for p in data["pricing"]:
                        summary += f"- {p.get('period', 'Standard')}: {p.get('price', 'N/A')} {p.get('currency', '')}\n"
                    summary += "\n"

                if data.get("flights"):
                    summary += f"### Flights: {len(data['flights'])} segments\n\n"

                if data.get("dailyBreakdown"):
                    summary += f"### Daily Breakdown: {len(data['dailyBreakdown'])} days\n"
                    for day in data["dailyBreakdown"][:3]:
                        summary += f"- **Day {day.get('day', '?')}:** {day.get('title', '')}\n"
                    if len(data["dailyBreakdown"]) > 3:
                        summary += f"- ... and {len(data['dailyBreakdown']) - 3} more days\n"

                if result.get("output_path"):
                    summary += f"\n\nFull analysis saved to `{result['output_path']}`"

                emit_fn("agent_response", {
                    "type": "response",
                    "content": summary,
                    "agent": "Analysis Agent",
                    "data": result,
                    "timestamp": datetime.utcnow().isoformat(),
                })
            else:
                emit_fn("agent_response", {
                    "type": "error",
                    "content": f"Analysis failed: {result.get('error', 'Unknown error')}",
                    "timestamp": datetime.utcnow().isoformat(),
                })
        else:
            emit_fn("agent_response", {
                "type": "response",
                "content": (
                    "To analyse an itinerary, please **upload a PDF file** first, "
                    "then say `analyze itinerary`.\n\n"
                    "**Supported formats:** PDF, DOCX, TXT\n\n"
                    "**What I extract:**\n"
                    "- Tour name, duration, destinations\n"
                    "- Pricing (by period and currency)\n"
                    "- Flight details\n"
                    "- Inclusions / exclusions\n"
                    "- Day-by-day breakdown with meals and activities\n\n"
                    "**Or use the API:**\n"
                    "```\nPOST /api/itinerary/analyze  (upload file)\n"
                    "POST /api/itinerary/compare   (upload 2+ files)\n"
                    "POST /api/itinerary/market-intelligence\n```"
                ),
                "agent": "Analysis Agent",
                "timestamp": datetime.utcnow().isoformat(),
            })

    except Exception as e:
        logger.error(f"Itinerary analysis failed: {e}", exc_info=True)
        emit_fn("agent_response", {
            "type": "error",
            "content": f"Itinerary analysis error: {str(e)}",
            "timestamp": datetime.utcnow().isoformat(),
        })

    finally:
        emit_fn("agent_status", {
            "agent": "Analysis Agent",
            "status": "idle",
            "message": "Ready",
        })


def _handle_market_intelligence(message: str, file_path: str, emit_fn):
    """Handle market intelligence commands."""
    emit_fn("agent_status", {
        "agent": "Market Analysis Agent",
        "status": "working",
        "message": "Running market intelligence pipeline...",
    })

    try:
        if file_path:
            from tools.itinerary_tools import market_intelligence_tool
            result = market_intelligence_tool(
                document_paths=[file_path],
                include_web_research=True,
                fast_mode=True,
                save_output=True,
            )

            if result.get("success"):
                themes = result.get("dominant_themes", {})
                summary = (
                    f"## Market Intelligence Report\n\n"
                    f"**Main Destination:** {themes.get('main_destination', 'N/A')}\n"
                    f"**Main Theme:** {themes.get('main_theme', 'N/A')}\n\n"
                )

                if themes.get("top_destinations"):
                    summary += "### Top Destinations\n"
                    for dest, count in themes["top_destinations"].items():
                        summary += f"- {dest}: {count} product(s)\n"
                    summary += "\n"

                web = result.get("web_research", {})
                if web.get("packages_found"):
                    summary += f"### Web Research: {len(web['packages_found'])} competitor packages found\n\n"

                if result.get("final_report"):
                    summary += f"---\n\n{result['final_report']}"

                emit_fn("agent_response", {
                    "type": "response",
                    "content": summary,
                    "agent": "Market Analysis Agent",
                    "timestamp": datetime.utcnow().isoformat(),
                })
            else:
                emit_fn("agent_response", {
                    "type": "error",
                    "content": f"Market intelligence failed: {result.get('error', 'Unknown')}",
                    "timestamp": datetime.utcnow().isoformat(),
                })
        else:
            emit_fn("agent_response", {
                "type": "response",
                "content": (
                    "To run market intelligence, **upload itinerary PDF files** first.\n\n"
                    "The pipeline will:\n"
                    "1. Extract and validate documents\n"
                    "2. Analyse dominant themes, destinations and patterns\n"
                    "3. Search for competitor products online\n"
                    "4. Aggregate into a knowledge structure\n"
                    "5. Generate a strategic market report\n\n"
                    "**API:** `POST /api/itinerary/market-intelligence`"
                ),
                "agent": "Market Analysis Agent",
                "timestamp": datetime.utcnow().isoformat(),
            })

    except Exception as e:
        logger.error(f"Market intelligence failed: {e}", exc_info=True)
        emit_fn("agent_response", {
            "type": "error",
            "content": f"Market intelligence error: {str(e)}",
            "timestamp": datetime.utcnow().isoformat(),
        })

    finally:
        emit_fn("agent_status", {
            "agent": "Market Analysis Agent",
            "status": "idle",
            "message": "Ready",
        })


def _send_help(emit_fn):
    """Send help message."""
    emit_fn("agent_response", {
        "type": "response",
        "content": (
            "## Web365 ClawBot\n\n"
            "I automate expense recording and travel analysis for qualityb2bpackage.com.\n\n"
            "### Expense Processing:\n"
            "1. **Upload a file** (CSV, Excel, PDF, DOCX) with expense data\n"
            "2. I'll parse it and extract: group code, travel date, size, price\n"
            "3. Each record gets submitted to the website automatically\n"
            "4. You'll get the order numbers back as confirmation\n\n"
            "### Itinerary Analysis:\n"
            "- Upload a PDF and say **`analyze itinerary`** to extract structured data\n"
            "- Upload 2+ PDFs and say **`compare tour`** to get a comparison\n"
            "- Say **`market intelligence`** for a full market analysis pipeline\n\n"
            "### Supported commands:\n"
            "- Upload a file -> starts expense processing\n"
            "- `analyze itinerary` -> extract tour data from PDF\n"
            "- `compare tour` -> compare multiple itineraries\n"
            "- `market intelligence` -> run market analysis pipeline\n"
            "- `status` -> check current job status\n"
            "- `help` -> show this message\n\n"
            "### REST API:\n"
            "- `POST /api/expenses` -> create single expense\n"
            "- `POST /api/batch-expenses` -> batch processing\n"
            "- `POST /api/parse` -> parse file without submitting\n"
            "- `GET /api/packages` -> list travel packages\n"
            "- `POST /api/itinerary/analyze` -> analyse itinerary PDF\n"
            "- `POST /api/itinerary/compare` -> compare itineraries\n"
            "- `POST /api/itinerary/market-intelligence` -> market analysis\n"
            "- `POST /api/itinerary/recommendations` -> strategic recs\n"
            "- `GET /api/jobs/<id>` -> check job status"
        ),
        "agent": "ClawBot",
        "timestamp": datetime.utcnow().isoformat(),
    })

"""
Admin Agent -- Administrative Assistant.

Handles administrative record management, data entry, and
system maintenance tasks on the QualityB2BPackage website.
"""

import logging
from datetime import datetime

from tools.browser_manager import BrowserManager, run_async
from tools import browser_tools
from config import Config

logger = logging.getLogger(__name__)


async def _manage_records(action: str, params: dict, emit_fn=None,
                          session_id: str = "default",
                          website_username: str = None,
                          website_password: str = None) -> dict:
    """Perform administrative record management tasks."""

    if emit_fn:
        emit_fn("agent_progress", {
            "agent": "Admin Agent",
            "message": "Logging into the system...",
        })

    login_result = await browser_tools.login(
        username=website_username, password=website_password, session_id=session_id,
    )
    if login_result["status"] != "success":
        return {
            "content": f"Login failed: {login_result['message']}",
            "data": None,
        }

    manager = BrowserManager.get_instance(session_id)
    page = await manager.get_page()
    results = {}

    try:
        if action == "list_expenses":
            # Navigate to charges_group listing
            if emit_fn:
                emit_fn("agent_progress", {
                    "agent": "Admin Agent",
                    "message": "Retrieving expense records...",
                })

            url = f"{Config.WEBSITE_URL.rstrip('/')}/charges_group"
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_timeout(2000)

            data = await browser_tools.scrape_table_data(page)
            await manager.screenshot("expense_list")

            results = {
                "action": "list_expenses",
                "count": len(data),
                "data": data,
                "timestamp": datetime.now().isoformat(),
            }

            summary = f"## Expense Records\n\n"
            summary += f"Found **{len(data)}** expense records.\n\n"
            if data[:5]:
                summary += "### Recent Entries\n"
                for i, row in enumerate(data[:5], 1):
                    summary += f"{i}. {' | '.join(str(v) for v in row.values())}\n"

        elif action == "list_bookings":
            if emit_fn:
                emit_fn("agent_progress", {
                    "agent": "Admin Agent",
                    "message": "Retrieving booking records...",
                })

            await page.goto(Config.BOOKING_URL, wait_until="networkidle")
            await page.wait_for_timeout(2000)

            data = await browser_tools.scrape_table_data(page)
            await manager.screenshot("booking_list")

            results = {
                "action": "list_bookings",
                "count": len(data),
                "data": data,
                "timestamp": datetime.now().isoformat(),
            }

            summary = f"## Booking Records\n\n"
            summary += f"Found **{len(data)}** booking records.\n\n"
            if data[:5]:
                summary += "### Recent Bookings\n"
                for i, row in enumerate(data[:5], 1):
                    summary += f"{i}. {' | '.join(str(v) for v in row.values())}\n"

        elif action == "create_expense":
            # Delegate to accounting agent for actual creation
            from agents.accounting_agent import handle_expense_task
            return handle_expense_task({"parameters": params}, emit_fn=emit_fn)

        else:
            summary = (
                "I can help with the following administrative tasks:\n"
                "- **List expenses**: View recent expense records\n"
                "- **List bookings**: View recent booking records\n"
                "- **Create expense**: Create a new expense entry\n\n"
                "Please specify what you'd like me to do."
            )
            results = {"action": "help", "available_actions": ["list_expenses", "list_bookings", "create_expense"]}

    except Exception as e:
        logger.error(f"Admin task failed: {e}", exc_info=True)
        summary = f"An error occurred: {str(e)}"
        results = {"action": action, "status": "failed", "error": str(e)}

    finally:
        await browser_tools.close_browser(session_id=session_id)

    return {"content": summary, "data": results}


def handle_admin_task(task_details: dict, emit_fn=None,
                      session_id: str = "default",
                      website_username: str = None,
                      website_password: str = None) -> dict:
    """Entry point called by the Assignment Agent."""
    action = task_details.get("action", "help")
    params = task_details.get("parameters", {})

    result = run_async(_manage_records(
        action, params, emit_fn,
        session_id=session_id,
        website_username=website_username,
        website_password=website_password,
    ))
    return result

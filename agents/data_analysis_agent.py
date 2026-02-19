"""
Data Analysis Agent -- Data Retrieval Specialist.

Extracts and validates booking data, seller reports, and financial
information from the QualityB2BPackage website.
"""

import json
import os
import logging
from datetime import datetime

from tools.browser_manager import BrowserManager, run_async
from tools import browser_tools
from config import Config

logger = logging.getLogger(__name__)


async def _scrape_booking_data(emit_fn=None, session_id: str = "default") -> dict:
    """Scrape booking data from /booking page."""
    manager = BrowserManager.get_instance(session_id)
    page = await manager.get_page()

    try:
        if emit_fn:
            emit_fn("agent_progress", {
                "agent": "Data Analysis Agent",
                "message": "Navigating to booking page...",
            })

        await page.goto(Config.BOOKING_URL, wait_until="networkidle")
        await page.wait_for_timeout(2000)
        await manager.screenshot("booking_page")

        # Extract table data
        bookings = await browser_tools.scrape_table_data(page)

        logger.info(f"Extracted {len(bookings)} booking records")
        return {
            "status": "success",
            "count": len(bookings),
            "data": bookings,
            "scraped_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Booking data extraction failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e), "data": []}


async def _scrape_seller_report(report_type: str = "tour", emit_fn=None, session_id: str = "default") -> dict:
    """Scrape seller performance report from /report/report_seller."""
    manager = BrowserManager.get_instance(session_id)
    page = await manager.get_page()

    try:
        if emit_fn:
            emit_fn("agent_progress", {
                "agent": "Data Analysis Agent",
                "message": f"Navigating to seller report ({report_type})...",
            })

        url = f"{Config.REPORT_SELLER_URL}?report_type={report_type}"
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(2000)
        await manager.screenshot("seller_report")

        # Extract table data
        report_data = await browser_tools.scrape_table_data(page)

        # Try to extract summary/totals
        summary = {}
        try:
            summary_elements = await page.query_selector_all(".summary, .total, tfoot td")
            for el in summary_elements:
                text = (await el.inner_text()).strip()
                if text:
                    summary[f"item_{len(summary)}"] = text
        except Exception:
            pass

        logger.info(f"Extracted {len(report_data)} report rows")
        return {
            "status": "success",
            "report_type": report_type,
            "count": len(report_data),
            "data": report_data,
            "summary": summary,
            "scraped_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Seller report extraction failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e), "data": []}


async def _run_data_analysis(analysis_type: str = "all", emit_fn=None,
                             session_id: str = "default",
                             website_username: str = None,
                             website_password: str = None) -> dict:
    """Run the complete data analysis workflow."""
    results = {}

    if emit_fn:
        emit_fn("agent_progress", {
            "agent": "Data Analysis Agent",
            "message": "Logging into the website...",
        })

    login_result = await browser_tools.login(
        username=website_username, password=website_password, session_id=session_id,
    )
    if login_result["status"] != "success":
        return {
            "content": f"Login failed: {login_result['message']}",
            "data": None,
        }

    if analysis_type in ("all", "booking"):
        booking_data = await _scrape_booking_data(emit_fn, session_id=session_id)
        results["bookings"] = booking_data

    if analysis_type in ("all", "report"):
        report_data = await _scrape_seller_report("tour", emit_fn, session_id=session_id)
        results["seller_report"] = report_data

    await browser_tools.close_browser(session_id=session_id)

    # Save results to file
    output_path = os.path.join(Config.DATA_DIR, "booking_data.json")
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Build summary
    summary = "## Data Analysis Results\n\n"

    if "bookings" in results:
        b = results["bookings"]
        summary += f"### Booking Data\n"
        summary += f"- Status: {b['status']}\n"
        summary += f"- Records found: {b.get('count', 0)}\n"
        if b["data"][:3]:
            summary += f"- Sample: {json.dumps(b['data'][:3], ensure_ascii=False, indent=2)}\n\n"

    if "seller_report" in results:
        r = results["seller_report"]
        summary += f"### Seller Report ({r.get('report_type', 'tour')})\n"
        summary += f"- Status: {r['status']}\n"
        summary += f"- Records found: {r.get('count', 0)}\n"
        if r.get("summary"):
            summary += f"- Summary: {json.dumps(r['summary'], ensure_ascii=False)}\n\n"

    summary += f"\nData saved to `{output_path}`"

    return {"content": summary, "data": results}


def handle_data_analysis_task(task_details: dict, emit_fn=None,
                              session_id: str = "default",
                              website_username: str = None,
                              website_password: str = None) -> dict:
    """Entry point called by the Assignment Agent."""
    params = task_details.get("parameters", {})
    analysis_type = params.get("analysis_type", "all")

    result = run_async(_run_data_analysis(
        analysis_type, emit_fn,
        session_id=session_id,
        website_username=website_username,
        website_password=website_password,
    ))
    return result

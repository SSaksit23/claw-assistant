"""
Expense Service -- The 7-step expense recording workflow.

Steps:
1. Receive uploaded document from user
2. Parse and extract data fields
3. Classify each field (group code, travel date, size, price)
4. Navigate to order creation page on qualityb2bpackage.com
5. Fill in the form with extracted data
6. Submit and capture the order number
7. Return status to the user

Supports two modes:
- Direct mode: Flask app does browser automation directly
- n8n mode: Flask triggers n8n webhook, n8n calls back to Flask API
"""

import os
import json
import uuid
import logging
from datetime import datetime
from typing import Optional, Callable

from config import Config
from services.document_parser import parse_file
from services import n8n_integration
from tools.browser_manager import BrowserManager, run_async
from tools import browser_tools

logger = logging.getLogger(__name__)

# In-memory job tracker
_jobs = {}


def get_job(job_id: str) -> Optional[dict]:
    """Get job status by ID."""
    return _jobs.get(job_id)


def start_expense_job(
    file_path: str,
    emit_fn: Optional[Callable] = None,
) -> dict:
    """
    Start the expense recording workflow.

    This is the main entry point called from the WebSocket handler.
    """
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "id": job_id,
        "status": "started",
        "file_path": file_path,
        "started_at": datetime.now().isoformat(),
        "steps": [],
        "results": [],
    }

    _emit(emit_fn, "agent_status", {
        "agent": "Assignment Agent",
        "status": "working",
        "message": "Processing your file...",
    })

    # ── Step 1: Parse the uploaded document ──
    _update_job(job_id, "step1_parsing", "Parsing uploaded document...")
    _emit(emit_fn, "agent_progress", {
        "agent": "Document Parser",
        "message": "**Step 1/7:** Parsing your document...",
    })

    parse_result = parse_file(file_path)

    if parse_result["status"] != "success" or not parse_result.get("records"):
        error_msg = "; ".join(parse_result.get("errors", ["No data extracted"]))
        _update_job(job_id, "failed", f"Parsing failed: {error_msg}")
        return {
            "content": f"Could not extract expense data from your file.\n\n**Errors:** {error_msg}",
            "job_id": job_id,
            "data": parse_result,
        }

    records = parse_result["records"]

    # ── Step 2 & 3: Data extracted and classified ──
    _update_job(job_id, "step2_extracted", f"Extracted {len(records)} records")
    _emit(emit_fn, "agent_progress", {
        "agent": "Document Parser",
        "message": f"**Step 2/7:** Extracted **{len(records)}** expense records.\n**Step 3/7:** Fields classified: {_describe_fields(records[0])}",
    })

    # Save parsed data
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    parsed_path = os.path.join(Config.DATA_DIR, f"parsed_{job_id}.json")
    with open(parsed_path, "w", encoding="utf-8") as f:
        json.dump({"job_id": job_id, "records": records, "parse_info": parse_result}, f, ensure_ascii=False, indent=2)

    # ── Decide: n8n or direct ──
    if n8n_integration.is_n8n_enabled():
        return _run_via_n8n(job_id, records, emit_fn)
    else:
        return _run_direct(job_id, records, emit_fn)


def _run_via_n8n(job_id: str, records: list, emit_fn) -> dict:
    """Route the job through n8n for workflow automation."""
    _update_job(job_id, "n8n_triggered", "Sending to n8n for processing...")
    _emit(emit_fn, "agent_progress", {
        "agent": "n8n Workflow",
        "message": "**Step 4-6:** Sending data to n8n automation workflow...",
    })

    callback_url = f"http://localhost:{Config.FLASK_PORT}/api/callback"
    result = n8n_integration.trigger_expense_workflow(records, callback_url, job_id)

    if result["status"] == "triggered":
        _update_job(job_id, "n8n_processing", "n8n is processing the records...")
        return {
            "content": (
                f"Your file has been parsed successfully!\n\n"
                f"**Records found:** {len(records)}\n\n"
                f"The data has been sent to the **n8n automation workflow** for processing. "
                f"Each record will be submitted to qualityb2bpackage.com automatically.\n\n"
                f"Job ID: `{job_id}` -- I'll update you when the results come back."
            ),
            "job_id": job_id,
            "data": {"records": records, "n8n_status": result},
        }
    else:
        # n8n failed -- fall back to direct mode
        _emit(emit_fn, "agent_progress", {
            "agent": "System",
            "message": f"n8n not available ({result.get('message', '')}). Falling back to direct automation...",
        })
        return _run_direct(job_id, records, emit_fn)


def _run_direct(job_id: str, records: list, emit_fn) -> dict:
    """Execute browser automation directly (no n8n)."""
    result = run_async(_run_direct_async(job_id, records, emit_fn))
    return result


async def _run_direct_async(job_id: str, records: list, emit_fn) -> dict:
    """Async implementation of the direct expense automation flow."""

    # ── Step 4: Login and navigate ──
    _update_job(job_id, "step4_login", "Logging in to qualityb2bpackage.com...")
    _emit(emit_fn, "agent_status", {
        "agent": "Accounting Agent",
        "status": "working",
        "message": "Logging in...",
    })
    _emit(emit_fn, "agent_progress", {
        "agent": "Accounting Agent",
        "message": "**Step 4/7:** Logging into qualityb2bpackage.com...",
    })

    login_result = await browser_tools.login()
    if login_result["status"] != "success":
        _update_job(job_id, "failed", f"Login failed: {login_result['message']}")
        return {
            "content": f"Login failed: {login_result['message']}",
            "job_id": job_id,
            "data": None,
        }

    # ── Step 5 & 6: Process each record ──
    results = []
    total = len(records)
    success_count = 0
    fail_count = 0

    for i, record in enumerate(records, 1):
        tour_code = record.get("tour_code", "N/A")

        _emit(emit_fn, "agent_progress", {
            "agent": "Accounting Agent",
            "message": f"**Step 5/7:** Processing record {i}/{total}: `{tour_code}`...",
        })

        entry_result = await _process_one_expense(record)
        results.append(entry_result)

        if entry_result["status"] == "success":
            success_count += 1
            _emit(emit_fn, "agent_progress", {
                "agent": "Accounting Agent",
                "message": f"**Step 6/7:** Record {i} submitted. Order: `{entry_result.get('expense_number', 'N/A')}`",
            })
        else:
            fail_count += 1
            _emit(emit_fn, "agent_progress", {
                "agent": "Accounting Agent",
                "message": f"Record {i} failed: {entry_result.get('error', 'Unknown error')}",
            })

    # Close browser
    await browser_tools.close_browser()

    # ── Step 7: Return results ──
    _update_job(job_id, "completed", f"Processed {total} records")
    _jobs[job_id]["results"] = results

    _emit(emit_fn, "agent_status", {
        "agent": "Accounting Agent",
        "status": "done",
        "message": f"Done: {success_count} OK, {fail_count} failed",
    })

    # Build summary message
    summary = f"## Expense Processing Complete\n\n"
    summary += f"**Job ID:** `{job_id}`\n"
    summary += f"**Total records:** {total}\n"
    summary += f"**Successful:** {success_count}\n"
    summary += f"**Failed:** {fail_count}\n\n"

    if success_count > 0:
        summary += "### Successful Entries\n"
        summary += "| Tour Code | Amount | Order Number |\n"
        summary += "|-----------|--------|--------------|\n"
        for r in results:
            if r["status"] == "success":
                summary += f"| `{r['tour_code']}` | {r.get('amount', '')} {r.get('currency', 'THB')} | `{r.get('expense_number', 'N/A')}` |\n"
        summary += "\n"

    if fail_count > 0:
        summary += "### Failed Entries\n"
        for r in results:
            if r["status"] != "success":
                summary += f"- `{r['tour_code']}`: {r.get('error', 'Unknown error')}\n"

    # Save results
    results_path = os.path.join(Config.DATA_DIR, f"results_{job_id}.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({
            "job_id": job_id,
            "total": total,
            "success_count": success_count,
            "fail_count": fail_count,
            "results": results,
        }, f, ensure_ascii=False, indent=2)

    return {
        "content": summary,
        "job_id": job_id,
        "data": {"results": results, "success_count": success_count, "fail_count": fail_count},
    }


async def _process_one_expense(record: dict) -> dict:
    """Process a single expense record through the website form."""
    tour_code = record.get("tour_code", "")
    amount = record.get("amount", 0)
    description = record.get("description", tour_code)
    charge_type = record.get("charge_type", "other")
    currency = record.get("currency", "THB")
    exchange_rate = record.get("exchange_rate", 1.0)
    payment_date = record.get("travel_date") or datetime.now().strftime("%d/%m/%Y")
    program_code = record.get("program_code", "")

    try:
        # Navigate to form
        nav = await browser_tools.navigate_to_charges_form()
        if nav["status"] != "success":
            return {"tour_code": tour_code, "status": "failed", "error": f"Navigation: {nav['message']}"}

        # Select program and tour
        sel = await browser_tools.select_program_and_tour(
            program_name=program_code, tour_code=tour_code,
        )
        if sel["status"] != "success":
            return {"tour_code": tour_code, "status": "failed", "error": f"Selection: {sel['message']}"}

        # Fill form
        fill = await browser_tools.fill_expense_form(
            payment_date=payment_date,
            description=description,
            charge_type=charge_type,
            amount=amount,
            currency=currency,
            exchange_rate=exchange_rate,
        )
        if fill["status"] != "success":
            return {"tour_code": tour_code, "status": "failed", "error": f"Form fill: {fill['message']}"}

        # Submit
        sub = await browser_tools.submit_form()
        if sub["status"] != "success":
            return {"tour_code": tour_code, "status": "failed", "error": f"Submit: {sub['message']}"}

        # Extract order number
        ext = await browser_tools.extract_order_number()

        return {
            "tour_code": tour_code,
            "program_code": program_code,
            "amount": amount,
            "currency": currency,
            "status": "success",
            "expense_number": ext.get("expense_number", "UNKNOWN"),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Expense failed for {tour_code}: {e}", exc_info=True)
        return {
            "tour_code": tour_code,
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


def process_single_expense_api(data: dict) -> dict:
    """
    API endpoint handler for processing a single expense.
    Called by n8n or external systems via POST /api/expenses.
    """
    record = {
        "tour_code": data.get("tour_code", ""),
        "program_code": data.get("program_code", ""),
        "amount": data.get("amount", 0),
        "pax": data.get("pax", 0),
        "currency": data.get("currency", "THB"),
        "description": data.get("description", ""),
        "charge_type": data.get("charge_type", "other"),
        "travel_date": data.get("travel_date"),
    }

    result = run_async(_process_one_expense(record))
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _update_job(job_id: str, status: str, message: str):
    if job_id in _jobs:
        _jobs[job_id]["status"] = status
        _jobs[job_id]["steps"].append({
            "status": status,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        })


def _emit(emit_fn, event: str, data: dict):
    if emit_fn:
        try:
            emit_fn(event, data)
        except Exception as e:
            logger.warning(f"Emit failed: {e}")


def _describe_fields(record: dict) -> str:
    """Describe what fields were found in a record."""
    parts = []
    if record.get("tour_code"):
        parts.append(f"group code=`{record['tour_code']}`")
    if record.get("travel_date"):
        parts.append(f"date=`{record['travel_date']}`")
    if record.get("pax"):
        parts.append(f"size=`{record['pax']}`")
    if record.get("amount"):
        parts.append(f"price=`{record['amount']}`")
    return ", ".join(parts) if parts else "basic fields detected"

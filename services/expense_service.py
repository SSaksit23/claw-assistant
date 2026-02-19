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
import re
import json
import uuid
import logging
from datetime import datetime
from typing import Optional, Callable

from openai import OpenAI
from config import Config
from services.document_parser import parse_file
from services import n8n_integration
from tools.browser_manager import BrowserManager, run_in_thread
from tools import browser_tools

logger = logging.getLogger(__name__)


def translate_supplier_name(name: str) -> str:
    """
    Translate a Chinese supplier name to English.
    Returns the original name if it's already in English/Thai or if
    translation fails.
    """
    if not name:
        return name

    # Quick check: if it's mostly ASCII or Thai, no translation needed
    non_ascii = sum(1 for c in name if ord(c) > 0x7F)
    has_cjk = any('\u4e00' <= c <= '\u9fff' for c in name)

    if not has_cjk:
        return name

    try:
        client = OpenAI(api_key=Config.OPENAI_API_KEY, timeout=30.0)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Translate the following Chinese company/supplier name to English. "
                        "Return ONLY the English translation, nothing else."
                    ),
                },
                {"role": "user", "content": name},
            ],
            temperature=0,
            max_tokens=100,
        )
        translated = resp.choices[0].message.content.strip()
        logger.info("Translated supplier: '%s' -> '%s'", name, translated)
        return translated
    except Exception as e:
        logger.warning("Translation failed for '%s': %s", name, e)
        return name

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
    """Execute browser automation directly (no n8n).
    Runs in a real OS thread so Playwright's asyncio loop is isolated."""
    result = run_in_thread(_run_direct_async(job_id, records, emit_fn))
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
            "message": (
                f"**Step 5/7:** Processing record {i}/{total}: `{tour_code}`\n"
                f"- Looking up program code on /travelpackage...\n"
                f"- Extracting departure date from code..."
            ),
        })

        entry_result = await _process_one_expense(record)
        results.append(entry_result)

        if entry_result["status"] == "success":
            success_count += 1
            prog = entry_result.get("program_code", "?")
            dep = entry_result.get("depart_date", "?")
            _emit(emit_fn, "agent_progress", {
                "agent": "Accounting Agent",
                "message": (
                    f"**Step 6/7:** Record {i} submitted.\n"
                    f"- Program: `{prog}` | Depart: `{dep}`\n"
                    f"- Order: `{entry_result.get('expense_number', 'N/A')}`"
                ),
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
        summary += "| Tour Code | Description | Order Number |\n"
        summary += "|-----------|--------|--------------|\n"
        for r in results:
            if r["status"] == "success":
                desc = r.get("description", f"{r.get('amount', '')} {r.get('currency', 'THB')}")
                summary += f"| `{r['tour_code']}` | {desc} | `{r.get('expense_number', 'N/A')}` |\n"
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
    """
    Process a single expense record through the website form.

    Workflow:
    1. Extract departure date from tour code (last 6 digits = yymmdd)
    2. Look up the program code on /travelpackage using the group code
    3. Navigate to /charges_group/create
    4. Set date range around the departure date so the program appears
    5. Select the program using the program code
    6. Select the tour code in the period dropdown
    7. Fill description, type, amount, currency, remark
    8. Submit and capture order number

    Expected output format for the expense order:
        Supplier Name
        วันจ่าย : dd/mm/yy
        เลขที่ : <auto-generated>
        Code group : <tour_code>
        วันที่ <date range>
        รายละเอียด : <description> <unit_price> THB x <pax> PAX = <amount> THB
        ***ยอดเงินรวม: <amount> THB
    """
    tour_code = record.get("tour_code", "")
    pax = record.get("pax", 0)
    unit_price = record.get("unit_price", 0)
    amount = record.get("amount", 0)
    raw_description = record.get("description", tour_code)
    charge_type = record.get("charge_type", "flight")
    currency = record.get("currency", "THB")
    exchange_rate = record.get("exchange_rate", 1.0)
    supplier_name_raw = record.get("supplier_name", "")
    supplier_name = translate_supplier_name(supplier_name_raw)
    travel_date = record.get("travel_date", "")
    program_code = record.get("program_code", "")
    company_name = record.get("company_name", "")  # e.g. "Go365Travel", "2U Center"

    # ── Step A: Extract departure date from tour code ──
    depart_date = browser_tools.extract_date_from_tour_code(tour_code)
    if depart_date:
        logger.info("Departure date from tour code %s: %s", tour_code, depart_date)
    else:
        logger.info("No embedded date in tour code %s, using travel_date field", tour_code)

    # ── Step B: Look up program code on /travelpackage ──
    if not program_code:
        logger.info("Looking up program code for %s on /travelpackage...", tour_code)
        lookup = await browser_tools.search_program_code(tour_code)
        if lookup["status"] == "success":
            program_code = lookup["program_code"]
            logger.info("Program code resolved: %s", program_code)
        else:
            logger.warning("Program code lookup failed: %s", lookup.get("message"))

    # Calculate unit_price if only total and pax are known
    if not unit_price and amount and pax:
        unit_price = round(amount / pax)

    # Build the formatted description line:
    # "ค่ามัดจำตั่วเครื่องบิน 2160 THB x 21 PAX = 45360 THB"
    if pax and unit_price:
        formatted_desc = f"{raw_description} {unit_price} {currency} x {pax} PAX = {amount} {currency}"
    else:
        formatted_desc = f"{raw_description} {amount} {currency}"

    # Build remark with full expense order info
    remark_parts = []
    if supplier_name:
        remark_parts.append(supplier_name)
    remark_parts.append(f"Code group: {tour_code}")
    if travel_date:
        remark_parts.append(f"Date: {travel_date}")
    remark = "\n".join(remark_parts)

    # Payment date: use today
    payment_date = datetime.now().strftime("%d/%m/%Y")

    # ── Step C: Build date range for the charges form filter ──
    # The form requires a date range so the correct program shows in dropdowns.
    # Use the departure date ± 30 days, or fall back to a wide window.
    date_from, date_to = _build_date_range(depart_date)

    try:
        # Navigate to the create form
        nav = await browser_tools.navigate_to_charges_form()
        if nav["status"] != "success":
            return {"tour_code": tour_code, "status": "failed", "error": f"Navigation: {nav['message']}"}

        # Set date range and select program + tour code
        sel = await browser_tools.select_program_and_tour(
            program_name=program_code,
            tour_code=tour_code,
            date_from=date_from,
            date_to=date_to,
        )
        if sel["status"] != "success":
            logger.warning("Program selection returned: %s -- continuing anyway", sel.get("message"))

        # Fill section 1 (expense details)
        fill = await browser_tools.fill_expense_form(
            payment_date=payment_date,
            description=formatted_desc,
            charge_type=charge_type,
            amount=amount,
            currency=currency,
            exchange_rate=exchange_rate,
            remark=remark,
        )
        if fill["status"] != "success":
            return {"tour_code": tour_code, "status": "failed", "error": f"Form fill: {fill['message']}"}

        # Click "+ เพิ่มในค่าใช้จ่ายบริษัท" to reveal section 2
        add_btn = await browser_tools.click_add_company_expense()
        if add_btn["status"] != "success":
            logger.warning("Could not open company expense section: %s", add_btn.get("message"))

        # Fill section 2 (company expense)
        # Map charge_type to the Thai payment type category
        payment_type_map = {
            "flight": "ค่าตั๋วเครื่องบิน",
            "visa": "ค่าวีซ่า",
            "accommodation": "ค่าทัวร์/ค่าแลนด์",
            "tour_guide": "ค่าทัวร์/ค่าแลนด์",
            "meal": "ค่าทัวร์/ค่าแลนด์",
            "taxi": "ค่าใช้จ่ายเบ็ดเตล็ด",
            "other": "ค่าทัวร์/ค่าแลนด์",
        }
        company_remark_parts = []
        if tour_code:
            company_remark_parts.append(tour_code)
        if program_code:
            company_remark_parts.append(program_code)

        comp_fill = await browser_tools.fill_company_expense(
            company_name=company_name,
            payment_method="โอนเข้าบัญชี",
            supplier_name=supplier_name,
            amount=amount,
            payment_date=payment_date,
            payment_type=payment_type_map.get(charge_type, "ค่าทัวร์/ค่าแลนด์"),
            period=tour_code,
            remark=" / ".join(company_remark_parts),
        )
        if comp_fill["status"] != "success":
            logger.warning("Company expense fill issue: %s", comp_fill.get("message"))

        # Submit
        sub = await browser_tools.submit_form()
        if sub["status"] != "success":
            return {"tour_code": tour_code, "status": "failed", "error": f"Submit: {sub['message']}"}

        # Extract the expense number
        ext = await browser_tools.extract_order_number()

        return {
            "tour_code": tour_code,
            "program_code": program_code,
            "supplier_name": supplier_name,
            "amount": amount,
            "unit_price": unit_price,
            "pax": pax,
            "currency": currency,
            "description": formatted_desc,
            "depart_date": depart_date,
            "status": "success",
            "expense_number": ext.get("expense_number", "UNKNOWN"),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error("Expense failed for %s: %s", tour_code, e, exc_info=True)
        return {
            "tour_code": tour_code,
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


def _build_date_range(depart_date_str: str | None) -> tuple[str, str]:
    """
    Build a start/end date range (dd/mm/yyyy) for the charges form filter.

    If a departure date is available, uses depart_date ± 30 days.
    Otherwise falls back to a 90-day window around today.
    """
    from datetime import timedelta

    if depart_date_str:
        try:
            center = datetime.strptime(depart_date_str, "%d/%m/%Y")
        except ValueError:
            center = datetime.now()
    else:
        center = datetime.now()

    start = center - timedelta(days=30)
    end = center + timedelta(days=30)
    return start.strftime("%d/%m/%Y"), end.strftime("%d/%m/%Y")


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

    result = run_in_thread(_process_one_expense(record))
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
    if record.get("supplier_name"):
        parts.append(f"supplier=`{record['supplier_name']}`")
    if record.get("tour_code"):
        parts.append(f"group code=`{record['tour_code']}`")
    if record.get("travel_date"):
        parts.append(f"date=`{record['travel_date']}`")
    if record.get("pax"):
        parts.append(f"size=`{record['pax']}`")
    if record.get("unit_price"):
        parts.append(f"unit price=`{record['unit_price']}`")
    if record.get("amount"):
        parts.append(f"total=`{record['amount']}`")
    return ", ".join(parts) if parts else "basic fields detected"

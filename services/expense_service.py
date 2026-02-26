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
import asyncio
import logging
import queue as _queue
from datetime import datetime
from typing import Optional, Callable

# Get the REAL (unpatched) threading module so Event/Lock work correctly
# in real OS threads (Playwright thread) even when eventlet is active.
try:
    from eventlet.patcher import original as _original
    _threading = _original("threading")
except Exception:
    import threading as _threading


from config import Config
from services.document_parser import parse_file
from services import n8n_integration
from services import learning_service
from tools.browser_manager import BrowserManager, run_in_thread
from tools import browser_tools

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interactive input: ask the user and wait for their reply
# ---------------------------------------------------------------------------
_input_requests: dict[str, dict] = {}
_input_lock = _threading.Lock()


def submit_user_input(session_id: str, text: str):
    """Called by the websocket handler when the user replies to a pending question."""
    with _input_lock:
        req = _input_requests.get(session_id)
        if req:
            req["response"] = text
            req["event"].set()
            return True
    return False


def has_pending_input(session_id: str) -> bool:
    """Check whether the expense service is waiting for user input."""
    with _input_lock:
        return session_id in _input_requests


def _ask_user(emit_fn, session_id: str, question: str, timeout: float = 120) -> str | None:
    """
    Emit a question to the user and block until they reply (or timeout).

    Returns the user's answer or None on timeout.
    """
    evt = _threading.Event()
    with _input_lock:
        _input_requests[session_id] = {"question": question, "response": None, "event": evt}

    _emit(emit_fn, "agent_question", {
        "agent": "Accounting Agent",
        "question": question,
    })

    answered = evt.wait(timeout=timeout)

    with _input_lock:
        req = _input_requests.pop(session_id, {})

    if answered and req.get("response"):
        logger.info("User answered: %s", req["response"][:80])
        return req["response"]

    logger.warning("No user response within %ss for: %s", timeout, question[:60])
    return None


_GENERIC_CONTRACT_TERMS = {"甲方", "乙方", "丙方", "party a", "party b", "party c"}


def translate_supplier_name(name: str) -> str:
    """
    Return the supplier name as-is (no translation).
    Filters out generic contract role terms like 甲方/乙方 that are not
    real company names.
    """
    if not name:
        return name

    cleaned = name.strip().rstrip("-0123456789")
    if cleaned.lower() in _GENERIC_CONTRACT_TERMS:
        logger.info("Skipping generic contract term as supplier: '%s'", name)
        return ""

    return name

# In-memory job tracker
_jobs = {}

# Pending invoice reviews awaiting user confirmation (keyed by session_id)
_pending_reviews: dict[str, dict] = {}
_review_lock = _threading.Lock()


def get_job(job_id: str) -> Optional[dict]:
    """Get job status by ID."""
    return _jobs.get(job_id)


# ---------------------------------------------------------------------------
# Phase A: Invoice review — parse, analyse, present structured breakdown
# ---------------------------------------------------------------------------

def review_expense_invoice(
    file_path: str,
    emit_fn: Optional[Callable] = None,
    session_id: str = "default",
    company_name: str = "",
    expense_type: str = "",
) -> dict:
    """
    Parse an invoice file and return a structured cost-analysis review
    grouped by code group. Does NOT start browser automation — the user
    must confirm via confirm_and_execute_expense() first.
    """
    job_id = str(uuid.uuid4())[:8]
    job_start = datetime.now()
    _jobs[job_id] = {
        "id": job_id,
        "status": "reviewing",
        "file_path": file_path,
        "started_at": job_start.isoformat(),
        "steps": [],
        "results": [],
    }

    _emit(emit_fn, "agent_status", {
        "agent": "Accounting Agent",
        "status": "working",
        "message": "Reviewing your invoice...",
    })

    # Consult past learnings
    past_context = learning_service.get_relevant_learnings(
        task_description=f"expense invoice review cost breakdown {file_path}",
        agent="Accounting Agent",
        limit=5,
    )
    if past_context:
        logger.info("Consulting past learnings:\n%s", past_context)

    # Step 1: Parse the document
    _update_job(job_id, "parsing", "Parsing uploaded document...")
    _emit_timed(emit_fn, job_start, "Document Parser",
                "**Step 1:** Parsing your invoice...")

    parse_result = parse_file(file_path)

    if parse_result["status"] != "success" or not parse_result.get("records"):
        error_msg = "; ".join(parse_result.get("errors", ["No data extracted"]))
        _update_job(job_id, "failed", f"Parsing failed: {error_msg}")
        return {
            "content": f"Could not extract expense data from your file.\n\n**Errors:** {error_msg}",
            "job_id": job_id,
            "data": parse_result,
            "review_pending": False,
        }

    records = parse_result["records"]
    detected_currency = parse_result.get("detected_currency", "")
    supplier_name = parse_result.get("supplier_name", "")

    # Step 2: Group by tour_code and build cost breakdown
    _update_job(job_id, "analyzing", f"Analyzing {len(records)} records by code group...")
    _emit_timed(emit_fn, job_start, "Accounting Agent",
                f"**Step 2:** Analyzing cost structure ({len(records)} line items)...")

    grouped = _group_records_by_tour(records, expense_type=expense_type)
    primary_currency = detected_currency or records[0].get("currency", "THB")

    # Step 3: Build structured review per code group
    review_sections = []
    for group_key, items in grouped.items():
        display_code = group_key.split("__item")[0] if "__item" in group_key else group_key
        group_supplier = items[0].get("supplier_name", supplier_name) or supplier_name
        group_currency = items[0].get("currency", primary_currency)
        subtotal = sum(r.get("amount", 0) for r in items)

        section = f"### Cost Review — `{display_code}`\n\n"
        section += f"**Supplier:** {group_supplier or '_(not found)_'}\n"
        section += f"**Company:** {company_name or '_(pending — please provide)_'}\n"
        section += f"**Code Group:** `{display_code}`\n\n"
        section += "**Expenses:**\n\n"
        section += "| # | Type | Calculation | Amount |\n"
        section += "|---|------|-------------|--------|\n"

        for idx, item in enumerate(items, 1):
            label = item.get("expense_label") or CHARGE_TYPE_LABELS.get(
                item.get("charge_type", "other"), item.get("charge_type", "?"))
            amt = item.get("amount", 0)
            calc = item.get("calculation_note", "")
            if not calc:
                pax = item.get("pax")
                up = item.get("unit_price")
                qty = item.get("quantity")
                calc = _build_calculation_note(up, pax, qty, amt, group_currency)
            section += f"| {idx} | {label} | {calc} | **{amt:,.0f} {group_currency}** |\n"

        section += f"\n**Total: {subtotal:,.0f} {group_currency}**\n"
        review_sections.append(section)

    grand_total = sum(r.get("amount", 0) for r in records)
    review_header = f"## Invoice Review\n\n"
    review_header += f"**File:** `{os.path.basename(file_path)}`\n"
    review_header += f"**Groups found:** {len(grouped)} | **Line items:** {len(records)}\n"
    review_header += f"**Grand Total: {grand_total:,.0f} {primary_currency}**\n\n---\n\n"

    review_body = "\n---\n\n".join(review_sections)

    if not company_name:
        review_footer = "\n\n---\n\nPlease provide the **company name** and confirm to proceed."
    else:
        review_footer = "\n\n---\n\nPlease **confirm** to proceed with expense recording, or type corrections."

    review_content = review_header + review_body + review_footer

    # Save pending review for confirmation
    with _review_lock:
        _pending_reviews[session_id] = {
            "job_id": job_id,
            "file_path": file_path,
            "records": records,
            "grouped": grouped,
            "parse_result": parse_result,
            "company_name": company_name,
            "supplier_name": supplier_name,
            "expense_type": expense_type,
            "primary_currency": primary_currency,
            "created_at": datetime.now().isoformat(),
        }

    _update_job(job_id, "awaiting_confirmation", "Review presented, waiting for user confirmation")
    _emit(emit_fn, "agent_status", {
        "agent": "Accounting Agent",
        "status": "idle",
        "message": "Waiting for confirmation",
    })

    # Build code_groups list for the client to render editable inputs
    code_groups = []
    for group_key in grouped:
        display_code = group_key.split("__item")[0] if "__item" in group_key else group_key
        code_groups.append({"key": group_key, "display": display_code})

    return {
        "content": review_content,
        "job_id": job_id,
        "data": {
            "records": records,
            "grouped_count": len(grouped),
            "total": grand_total,
            "currency": primary_currency,
            "code_groups": code_groups,
        },
        "review_pending": True,
    }


def has_pending_review(session_id: str) -> bool:
    """Check whether there is an invoice review awaiting confirmation."""
    with _review_lock:
        return session_id in _pending_reviews


def get_pending_review(session_id: str) -> Optional[dict]:
    """Return the pending review data (without removing it)."""
    with _review_lock:
        return _pending_reviews.get(session_id)


def confirm_and_execute_expense(
    session_id: str,
    emit_fn: Optional[Callable] = None,
    company_name: str = "",
    website_username: str = None,
    website_password: str = None,
    expense_type: str = "",
    code_group_overrides: dict = None,
) -> dict:
    """
    Phase B: User confirmed the invoice review — proceed with browser
    automation using the previously parsed and reviewed data.

    code_group_overrides: optional dict mapping original group key to new
    tour code, e.g. {"GO1TAO6N...": "NEWTOURCODE123"}.
    """
    with _review_lock:
        pending = _pending_reviews.pop(session_id, None)

    if not pending:
        return {
            "content": "No pending invoice review found. Please upload a file first.",
            "data": None,
        }

    job_id = pending["job_id"]
    grouped = pending["grouped"]
    records = pending["records"]
    file_path = pending["file_path"]
    primary_currency = pending["primary_currency"]
    supplier_name = pending.get("supplier_name", "")

    if not company_name:
        company_name = pending.get("company_name", "")
    if not expense_type:
        expense_type = pending.get("expense_type", "")

    # Apply code group overrides if the user changed any tour codes
    if code_group_overrides:
        grouped = _apply_code_group_overrides(grouped, code_group_overrides)
        for items in grouped.values():
            for item in items:
                for old_key, new_code in code_group_overrides.items():
                    old_display = old_key.split("__item")[0] if "__item" in old_key else old_key
                    if item.get("tour_code") == old_display and new_code.strip():
                        item["tour_code"] = new_code.strip()
        for rec in records:
            for old_key, new_code in code_group_overrides.items():
                old_display = old_key.split("__item")[0] if "__item" in old_key else old_key
                if rec.get("tour_code") == old_display and new_code.strip():
                    rec["tour_code"] = new_code.strip()
        logger.info("Code group overrides applied: %s", code_group_overrides)

    job_start = datetime.now()
    _jobs[job_id]["status"] = "executing"
    _jobs[job_id]["steps"].append({
        "status": "confirmed",
        "message": f"User confirmed. Company: {company_name}",
        "timestamp": job_start.isoformat(),
    })

    _emit(emit_fn, "agent_status", {
        "agent": "Accounting Agent",
        "status": "working",
        "message": "Starting expense recording...",
    })

    _emit_timed(emit_fn, job_start, "Accounting Agent",
                f"**Confirmed!** Processing {len(grouped)} expense group(s) "
                f"for **{company_name or 'N/A'}**...")

    # Inject supplier_name and company_name into records for form filling
    for items in grouped.values():
        for item in items:
            if not item.get("supplier_name"):
                item["supplier_name"] = supplier_name
            if not item.get("company_name"):
                item["company_name"] = company_name

    # Save parsed data
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    parsed_path = os.path.join(Config.DATA_DIR, f"parsed_{job_id}.json")
    with open(parsed_path, "w", encoding="utf-8") as f:
        json.dump({
            "job_id": job_id,
            "records": records,
            "parse_info": pending["parse_result"],
        }, f, ensure_ascii=False, indent=2)

    # Decide: n8n or direct
    if n8n_integration.is_n8n_enabled():
        return _run_via_n8n(job_id, records, emit_fn)
    else:
        return _run_direct(
            job_id, grouped, emit_fn,
            session_id=session_id,
            website_username=website_username,
            website_password=website_password,
            company_name=company_name,
            expense_type=expense_type,
        )


def _build_calculation_note(
    unit_price, pax, quantity, amount, currency: str = ""
) -> str:
    """Build a human-readable calculation note from numeric fields."""
    parts = []
    if unit_price is not None and unit_price != 0:
        parts.append(f"{unit_price:,.0f}")
    if pax is not None and pax != 0:
        parts.append(f"x {int(pax)} pax")
    if quantity is not None and quantity not in (0, 1, None):
        parts.append(f"x {int(quantity)}")
    if parts:
        return " ".join(parts) + f" = {amount:,.0f}"
    if amount:
        return f"{amount:,.0f}"
    return ""


def _apply_code_group_overrides(grouped: dict, overrides: dict) -> dict:
    """Re-key the grouped dict when the user has changed tour codes.

    overrides: { original_group_key: new_tour_code }
    Only applies when the new code is non-empty and different from the original.
    """
    from collections import OrderedDict
    new_grouped = OrderedDict()
    for key, items in grouped.items():
        new_code = overrides.get(key, "").strip()
        if new_code and new_code != key:
            new_grouped[new_code] = items
        else:
            new_grouped[key] = items
    return new_grouped


def start_expense_job(
    file_path: str,
    emit_fn: Optional[Callable] = None,
    session_id: str = "default",
    website_username: str = None,
    website_password: str = None,
    company_name: str = "",
    expense_type: str = "",
) -> dict:
    """
    Start the expense recording workflow.

    This is the main entry point called from the WebSocket handler.
    """
    job_id = str(uuid.uuid4())[:8]
    job_start = datetime.now()
    _jobs[job_id] = {
        "id": job_id,
        "status": "started",
        "file_path": file_path,
        "started_at": job_start.isoformat(),
        "steps": [],
        "results": [],
    }

    _emit(emit_fn, "agent_status", {
        "agent": "Assignment Agent",
        "status": "working",
        "message": "Processing your file...",
    })

    # Consult past learnings before starting
    past_context = learning_service.get_relevant_learnings(
        task_description=f"expense recording browser automation form filling {file_path}",
        agent="Accounting Agent",
        limit=5,
    )
    if past_context:
        logger.info("Consulting past learnings:\n%s", past_context)

    # ── Step 1: Parse the uploaded document ──
    _update_job(job_id, "step1_parsing", "Parsing uploaded document...")
    _emit_timed(emit_fn, job_start, "Document Parser",
                "**Step 1/7:** Parsing your document...")

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
    detected_currency = parse_result.get("detected_currency", "")
    currency_evidence = parse_result.get("currency_evidence", "")

    # ── Step 2 & 3: Data extracted and classified ──
    _update_job(job_id, "step2_extracted", f"Extracted {len(records)} records")

    currency_note = ""
    if detected_currency:
        currency_note = f"\nCurrency: **{detected_currency}** ({currency_evidence})"

    # Group records by tour_code for multi-line form submissions
    type_label = {"flight": "Air Ticket", "land_tour": "Tour Fare",
                  "insurance": "Insurance", "misc": "Misc"}.get(expense_type, "")
    if expense_type:
        logger.info("Expense type selected: %s (%s)", expense_type, type_label)

    grouped = _group_records_by_tour(records, expense_type=expense_type)

    grand_total = sum(r.get("amount", 0) for r in records)
    primary_currency = detected_currency or records[0].get("currency", "THB")

    group_lines = []
    for tc, items in grouped.items():
        display_tc = tc.split("__item")[0] if "__item" in tc else tc
        subtotal = sum(r.get("amount", 0) for r in items)
        item_types = []
        for r in items:
            label = r.get("expense_label") or CHARGE_TYPE_LABELS.get(r.get("charge_type", "other"), r.get("charge_type", "?"))
            amt = r.get("amount", 0)
            item_types.append(f"{label} ({amt:,.0f})")
        items_str = " + ".join(item_types)
        group_lines.append(
            f"- `{display_tc}`: {items_str} = **{subtotal:,.0f} {primary_currency}** → 1 expense order"
        )
    group_summary = "\n".join(group_lines)

    type_note = f"\nType: **{type_label}**" if type_label else ""
    _emit_timed(emit_fn, job_start, "Document Parser",
                f"**Step 2/7:** Extracted **{len(records)}** line items "
                f"→ grouped into **{len(grouped)}** expense order{'s' if len(grouped) > 1 else ''}.{currency_note}{type_note}\n"
                f"**Grand Total: {grand_total:,.0f} {primary_currency}**\n"
                f"{group_summary}\n"
                f"Fields: {_describe_fields(records[0])}")

    # Save parsed data
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    parsed_path = os.path.join(Config.DATA_DIR, f"parsed_{job_id}.json")
    with open(parsed_path, "w", encoding="utf-8") as f:
        json.dump({"job_id": job_id, "records": records, "parse_info": parse_result}, f, ensure_ascii=False, indent=2)

    # ── Decide: n8n or direct ──
    if n8n_integration.is_n8n_enabled():
        return _run_via_n8n(job_id, records, emit_fn)
    else:
        return _run_direct(
            job_id, grouped, emit_fn,
            session_id=session_id,
            website_username=website_username,
            website_password=website_password,
            company_name=company_name,
            expense_type=expense_type,
        )


def start_manual_expense_job(
    params: dict,
    emit_fn: Optional[Callable] = None,
    session_id: str = "default",
    website_username: str = None,
    website_password: str = None,
    company_name: str = "",
    expense_type: str = "",
) -> dict:
    """
    Start the expense recording workflow from manually typed chat parameters
    (no file upload needed).

    params should contain at minimum: tour_code.
    Optional: amount, unit_price, pax, currency, charge_type, expense_label,
              supplier_name, travel_date, program_code, description.
    """
    tour_code = params.get("tour_code", "").strip()
    if not tour_code:
        return {
            "content": "I need a **tour/group code** to create an expense. "
                       "Please provide it (e.g., `BTNRTXJ260313W02`).",
            "data": None,
        }

    job_id = str(uuid.uuid4())[:8]
    job_start = datetime.now()
    _jobs[job_id] = {
        "id": job_id,
        "status": "started",
        "source": "manual_entry",
        "started_at": job_start.isoformat(),
        "steps": [],
        "results": [],
    }

    _emit(emit_fn, "agent_status", {
        "agent": "Accounting Agent",
        "status": "working",
        "message": "Processing manual expense entry...",
    })

    pax = params.get("pax")
    unit_price = params.get("unit_price")
    amount = params.get("amount")

    if pax is not None:
        try:
            pax = int(float(pax))
        except (ValueError, TypeError):
            pax = None
    if unit_price is not None:
        try:
            unit_price = float(unit_price)
        except (ValueError, TypeError):
            unit_price = None
    if amount is not None:
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            amount = None

    if not amount and unit_price and pax:
        amount = unit_price * pax

    if not amount:
        return {
            "content": "I need the **amount** (or unit_price x pax) to create this expense. "
                       "Please provide the numbers.",
            "data": None,
        }

    currency = params.get("currency", "THB") or "THB"
    charge_type = params.get("charge_type", "other") or "other"
    expense_label = params.get("expense_label") or CHARGE_TYPE_LABELS.get(charge_type, charge_type)

    record = {
        "tour_code": tour_code,
        "program_code": params.get("program_code", ""),
        "travel_date": params.get("travel_date", ""),
        "pax": pax,
        "unit_price": unit_price,
        "amount": amount,
        "currency": currency,
        "charge_type": charge_type,
        "expense_label": expense_label,
        "supplier_name": params.get("supplier_name", ""),
        "description": params.get("description", expense_label),
        "exchange_rate": params.get("exchange_rate", 1.0),
    }

    if not company_name:
        company_name = params.get("company_name", "")

    grouped = {tour_code: [record]}

    _emit_timed(emit_fn, job_start, "Accounting Agent",
                f"**Manual entry:** `{tour_code}` -- {expense_label}: "
                f"**{amount:,.0f} {currency}**"
                + (f" ({pax} pax x {unit_price:,.0f})" if pax and unit_price else ""))

    return _run_direct(
        job_id, grouped, emit_fn,
        session_id=session_id,
        website_username=website_username,
        website_password=website_password,
        company_name=company_name,
        expense_type=expense_type,
    )


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


def _run_direct(
    job_id: str, grouped_records: dict, emit_fn,
    session_id: str = "default",
    website_username: str = None,
    website_password: str = None,
    company_name: str = "",
    expense_type: str = "",
) -> dict:
    """Execute browser automation directly (no n8n).

    grouped_records: { tour_code: [record, ...], ... }

    Runs in a real OS thread so Playwright's asyncio loop is isolated.
    IMPORTANT: SocketIO emit cannot be called from a non-eventlet thread
    (causes greenlet.error and hangs). So we collect progress messages in
    a list and replay them back in the eventlet greenlet after the OS
    thread finishes each record, using a polling approach.
    """
    import queue as _queue
    import eventlet

    progress_queue: _queue.Queue = _queue.Queue()

    def thread_safe_emit(event: str, data: dict):
        """Drop messages onto a thread-safe queue instead of calling SocketIO."""
        progress_queue.put((event, data))

    def _drain_queue():
        """Flush queued progress messages from the eventlet greenlet."""
        while not progress_queue.empty():
            try:
                event, data = progress_queue.get_nowait()
                _emit(emit_fn, event, data)
            except _queue.Empty:
                break

    # Pre-emit step 4 from the safe eventlet greenlet
    job_start = _jobs.get(job_id, {}).get("started_at", datetime.now().isoformat())
    try:
        job_start_dt = datetime.fromisoformat(job_start)
    except (ValueError, TypeError):
        job_start_dt = datetime.now()

    _update_job(job_id, "step4_login", "Logging in to qualityb2bpackage.com...")
    _emit(emit_fn, "agent_status", {
        "agent": "Accounting Agent",
        "status": "working",
        "message": "Logging in...",
    })
    _emit_timed(emit_fn, job_start_dt, "Accounting Agent",
                "**Step 4/7:** Logging into qualityb2bpackage.com...")

    # Run the async Playwright work in a real OS thread, passing the
    # thread-safe emit wrapper so it never touches eventlet internals.
    # We poll the thread and drain queued progress in the eventlet greenlet
    # so the user sees live updates.
    result_q: _queue.Queue = _queue.Queue()
    coro = _run_direct_async(
        job_id, grouped_records, thread_safe_emit,
        session_id=session_id,
        website_username=website_username,
        website_password=website_password,
        company_name=company_name,
        expense_type=expense_type,
    )

    def _worker():
        import asyncio as _aio
        loop = _aio.new_event_loop()
        _aio.set_event_loop(loop)
        try:
            res = loop.run_until_complete(coro)
            result_q.put(("ok", res))
        except Exception as exc:
            result_q.put(("error", exc))
        finally:
            loop.close()

    try:
        from eventlet.patcher import original as _original
        _real_threading = _original("threading")
    except Exception:
        import threading as _real_threading

    t = _real_threading.Thread(target=_worker, daemon=True)
    t.start()

    while t.is_alive():
        _drain_queue()
        eventlet.sleep(0.3)

    # Final drain after thread completes
    _drain_queue()

    status, value = result_q.get_nowait()
    if status == "error":
        raise value
    return value


async def _run_direct_async(
    job_id: str, grouped_records: dict, emit_fn,
    session_id: str = "default",
    website_username: str = None,
    website_password: str = None,
    company_name: str = "",
    expense_type: str = "",
) -> dict:
    """Async implementation of the direct expense automation flow.

    grouped_records: { tour_code: [record, ...], ... }

    NOTE: emit_fn here is the thread-safe queue wrapper, NOT the real
    SocketIO emit.  Safe to call from the Playwright OS thread.
    """

    from tools.browser_manager import BrowserManager

    job_start = datetime.now()
    BrowserManager.acquire(session_id)

    try:
        return await _run_direct_async_inner(
            job_id, grouped_records, emit_fn, job_start,
            session_id=session_id,
            website_username=website_username,
            website_password=website_password,
            company_name=company_name,
            expense_type=expense_type,
        )
    finally:
        BrowserManager.release(session_id)


async def _run_direct_async_inner(
    job_id, grouped_records, emit_fn, job_start,
    session_id="default", website_username=None, website_password=None,
    company_name="", expense_type="",
):
    _emit_timed(emit_fn, job_start, "Accounting Agent", "Logging in...")
    login_result = await browser_tools.login(
        username=website_username,
        password=website_password,
        session_id=session_id,
    )
    if login_result["status"] != "success":
        _update_job(job_id, "failed", f"Login failed: {login_result['message']}")
        return {
            "content": f"Login failed: {login_result['message']}",
            "job_id": job_id,
            "data": None,
        }
    _emit_timed(emit_fn, job_start, "Accounting Agent", "Login successful")

    # ── Step 5 & 6: Process each tour group ──
    results = []
    total = len(grouped_records)
    success_count = 0
    fail_count = 0

    for i, (group_key, line_items) in enumerate(grouped_records.items(), 1):
        record_start = datetime.now()
        # For split-mode keys like "GO1TAO5N...260314__item0", use the real tour code
        tour_code = group_key.split("__item")[0] if "__item" in group_key else group_key
        n_items = len(line_items)
        item_types = ", ".join(r.get("charge_type", "?") for r in line_items)
        currency = line_items[0].get("currency", "THB")
        total_amount = sum(r.get("amount", 0) for r in line_items)

        _emit_timed(emit_fn, job_start, "Accounting Agent",
                    f"**Group {i}/{total}:** `{tour_code}` -- "
                    f"{n_items} line item{'s' if n_items > 1 else ''} "
                    f"({item_types}) | {total_amount:,.0f} {currency}")

        try:
            import asyncio as _aio
            timeout_secs = 120 + (n_items * 30)
            entry_result = await _aio.wait_for(
                _process_tour_group(
                    tour_code, line_items, emit_fn, job_start,
                    session_id=session_id,
                    website_username=website_username,
                    website_password=website_password,
                    company_name=company_name,
                    expense_type=expense_type,
                ),
                timeout=timeout_secs,
            )
        except Exception as timeout_err:
            _emit_timed(emit_fn, job_start, "Accounting Agent",
                        f"**Group {i}/{total} TIMEOUT** -- exceeded {timeout_secs}s, skipping")
            entry_result = {
                "tour_code": tour_code,
                "status": "failed",
                "error": f"Timed out after {timeout_secs}s: {timeout_err}",
                "timestamp": datetime.now().isoformat(),
            }
        results.append(entry_result)

        elapsed_rec = (datetime.now() - record_start).total_seconds()

        if entry_result["status"] == "success":
            success_count += 1
            prog = entry_result.get("program_code", "?")
            dep = entry_result.get("depart_date", "?")
            rows_desc = entry_result.get("rows_description", "")
            _emit_timed(emit_fn, job_start, "Accounting Agent",
                        f"**Group {i}/{total} done** ({elapsed_rec:.1f}s)\n"
                        f"- Program: `{prog}` | Depart: `{dep}`\n"
                        f"- Items: {rows_desc}\n"
                        f"- Order: `{entry_result.get('expense_number', 'N/A')}`")
        else:
            fail_count += 1
            _emit_timed(emit_fn, job_start, "Accounting Agent",
                        f"**Group {i}/{total} FAILED** ({elapsed_rec:.1f}s)\n"
                        f"- Error: {entry_result.get('error', 'Unknown error')}")

    # ── Step 7: Return results ──
    total_elapsed = (datetime.now() - job_start).total_seconds()
    total_items = sum(len(items) for items in grouped_records.values())
    _update_job(job_id, "completed", f"Processed {total} groups ({total_items} items) in {total_elapsed:.0f}s")
    _jobs[job_id]["results"] = results

    _emit_timed(emit_fn, job_start, "Accounting Agent",
                f"**Step 7/7: COMPLETE** -- {success_count} OK, {fail_count} failed "
                f"({total} groups, {total_items} line items, {total_elapsed:.0f}s)")

    _emit(emit_fn, "agent_status", {
        "agent": "Accounting Agent",
        "status": "done",
        "message": f"Done: {success_count} OK, {fail_count} failed",
    })

    # Build summary table
    summary = f"## Expense Processing Complete\n\n"
    summary += f"**Job ID:** `{job_id}` | **Duration:** {total_elapsed:.0f}s "
    summary += f"| **Groups:** {total} | **Items:** {total_items} "
    summary += f"| **OK:** {success_count} | **Failed:** {fail_count}\n\n"

    if results:
        summary += "| # | Tour Code | Supplier | Items | Amount | Currency | Order No. | Status |\n"
        summary += "|---|-----------|----------|-------|--------|----------|-----------|--------|\n"
        for idx, r in enumerate(results, 1):
            tc = r.get("tour_code", "?")
            supplier = r.get("supplier_name", "")[:30]
            items_desc = r.get("rows_description", "")[:40]
            total_amt = r.get("total_amount", 0)
            cur = r.get("currency", "THB")
            order_no = r.get("expense_number", "N/A")
            status = r.get("status", "?")
            status_icon = "OK" if status == "success" else "FAILED"

            if status == "success":
                summary += f"| {idx} | `{tc}` | {supplier} | {items_desc} | {total_amt:,.0f} | {cur} | `{order_no}` | {status_icon} |\n"
            else:
                error_msg = r.get("error", "Unknown")[:30]
                summary += f"| {idx} | `{tc}` | {supplier} | {items_desc} | - | {cur} | - | {error_msg} |\n"
        summary += "\n"

    # Grand totals for successful entries
    if success_count > 0:
        by_currency = {}
        for r in results:
            if r["status"] == "success":
                cur = r.get("currency", "THB")
                by_currency[cur] = by_currency.get(cur, 0) + r.get("total_amount", 0)
        totals_str = " | ".join(f"**{amt:,.0f} {cur}**" for cur, amt in by_currency.items())
        summary += f"**Grand Total:** {totals_str}\n\n"

    if fail_count > 0:
        summary += "### Failed Entries\n"
        for r in results:
            if r["status"] != "success":
                summary += f"- `{r['tour_code']}`: {r.get('error', 'Unknown error')}\n"
        summary += "\n"

    # Generate CSV export
    csv_filename = f"expenses_{job_id}.csv"
    csv_path = os.path.join(Config.DATA_DIR, csv_filename)
    _write_results_csv(csv_path, results, job_id)

    summary += f'📥 [**Download CSV Report**](/api/export/{job_id})\n'

    # Save results JSON
    results_path = os.path.join(Config.DATA_DIR, f"results_{job_id}.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({
            "job_id": job_id,
            "total_groups": total,
            "total_items": total_items,
            "success_count": success_count,
            "fail_count": fail_count,
            "results": results,
        }, f, ensure_ascii=False, indent=2)

    return {
        "content": summary,
        "job_id": job_id,
        "data": {
            "results": results,
            "success_count": success_count,
            "fail_count": fail_count,
            "csv_path": csv_path,
        },
    }


PAYMENT_TYPE_MAP = {
    "flight": "ค่าตั๋วเครื่องบิน",
    "visa": "ค่าวีซ่า",
    "accommodation": "ค่าทัวร์/ค่าแลนด์",
    "tour_guide": "ค่าทัวร์/ค่าแลนด์",
    "meal": "ค่าทัวร์/ค่าแลนด์",
    "taxi": "ค่าใช้จ่ายเบ็ดเตล็ด",
    "land_tour": "ค่าทัวร์/ค่าแลนด์",
    "single_supplement": "ค่าทัวร์/ค่าแลนด์",
    "service_fee": "ค่าทัวร์/ค่าแลนด์",
    "guide_tip": "เบี้ยเลี้ยง (ค่าจ้างมัคคุเทศก์และหัวหน้าทัวร์)",
    "transport": "ค่าใช้จ่ายเบ็ดเตล็ด",
    "insurance": "ค่าประกันภัย",
    "entrance_fee": "ค่าทัวร์/ค่าแลนด์",
    "commission": "ค่าคอมมิชชั่น",
    "other": "ค่าใช้จ่ายเบ็ดเตล็ด",
}

CHARGE_TYPE_LABELS = {
    "flight": "Airline Ticket",
    "land_tour": "Tour Fare",
    "single_supplement": "Single Room Supplement",
    "service_fee": "Service Fee",
    "guide_tip": "Guide Fee / Tips",
    "visa": "Visa Fee",
    "accommodation": "Accommodation",
    "meal": "Meals",
    "transport": "Transport",
    "insurance": "Insurance",
    "entrance_fee": "Entrance Fee",
    "commission": "Commission",
    "other": "Other",
}


async def _process_tour_group(
    tour_code: str, line_items: list, emit_fn=None, job_start=None,
    session_id: str = "default",
    website_username: str = None,
    website_password: str = None,
    company_name: str = "",
    expense_type: str = "",
) -> dict:
    """Process a tour group (one or more line items) through a single form submission."""
    _job_start = job_start or datetime.now()

    def _progress(msg):
        _emit_timed(emit_fn, _job_start, "Accounting Agent", f"`{tour_code}` {msg}")

    first = line_items[0]
    supplier_name_raw = first.get("supplier_name", "")
    travel_date = first.get("travel_date", "")
    program_code = first.get("program_code", "")
    # company_name comes from the user's message (e.g., "Go365Travel");
    # fall back to record-level value or empty.
    if not company_name:
        company_name = first.get("company_name", "")
    currency = first.get("currency", "THB")
    exchange_rate = first.get("exchange_rate", 1.0)

    total_amount = sum(r.get("amount", 0) for r in line_items)

    # ── Step A: Clean supplier name (keep original, filter generic terms) ──
    supplier_name = translate_supplier_name(supplier_name_raw)
    logger.info("Supplier name: raw='%s' -> final='%s', company='%s'", supplier_name_raw, supplier_name, company_name)

    # If supplier name is missing from the document, ask the user
    if not supplier_name:
        _progress("supplier name not found in document, asking user...")
        user_answer = _ask_user(
            emit_fn, session_id,
            f"I couldn't find the supplier/pay-to name in the document for tour `{tour_code}`.\n"
            f"Please type the **supplier name** (ชื่อ/บริษัทที่สั่งจ่าย):",
            timeout=180,
        )
        if user_answer:
            supplier_name = user_answer.strip()
            _progress(f"supplier set to: **{supplier_name}**")
        else:
            _progress("no supplier name provided, leaving blank")

    # ── Step B: Extract departure date from tour code ──
    depart_date = browser_tools.extract_date_from_tour_code(tour_code)
    if depart_date:
        logger.info("Departure date from tour code %s: %s", tour_code, depart_date)
    else:
        logger.info("No embedded date in tour code %s, using travel_date field", tour_code)

    # ── Step C: Look up program code on /travelpackage ──
    if not program_code:
        _progress("searching program code on /travelpackage...")
        try:
            lookup = await browser_tools.search_program_code(tour_code, session_id=session_id)
        except Exception as search_err:
            logger.warning("Program code search failed: %s", search_err)
            lookup = {"status": "failed", "message": str(search_err)}
        if lookup["status"] == "success":
            program_code = lookup["program_code"]
            _progress(f"found program: `{program_code}`")
        else:
            _progress("program code not found, continuing...")
            logger.warning("Program code lookup failed: %s", lookup.get("message"))

    # Build expense rows for multi-line form filling
    rows_for_form = []
    rows_description_parts = []
    formatted_desc_lines = []

    for item in line_items:
        desc = item.get("description", "")
        ct = item.get("charge_type", "other")
        amt = item.get("amount", 0)
        pax = item.get("pax")
        up = item.get("unit_price")
        qty = item.get("quantity")
        calc_note = item.get("calculation_note")

        if not up and amt and pax:
            up = round(amt / pax)

        expense_label = item.get("expense_label") or CHARGE_TYPE_LABELS.get(ct, ct)

        rows_description_parts.append(f"{expense_label}: {amt:,.0f} {currency}")

        item_desc = _format_expense_description(
            expense_label=expense_label,
            travel_date=item.get("travel_date", travel_date),
            travel_date_start=item.get("travel_date_start"),
            travel_date_end=item.get("travel_date_end"),
            pax=pax,
            unit_price=up,
            quantity=qty,
            amount=amt,
            currency=currency,
            tour_code=tour_code,
            calculation_note=calc_note,
        )
        formatted_desc_lines.append(item_desc)

        rows_for_form.append({
            "description": desc,
            "charge_type": ct,
            "amount": amt,
            "currency": currency,
            "exchange_rate": exchange_rate,
            "pax": pax,
            "unit_price": up,
            "expense_label": expense_label,
            "formatted_description": item_desc,
        })

    rows_description = " | ".join(rows_description_parts)

    # Build the structured remark: Supplier, Company, Code Group, expenses, total
    remark_parts = []
    if supplier_name:
        remark_parts.append(f"Supplier: {supplier_name}")
    if company_name:
        remark_parts.append(f"Company: {company_name}")
    remark_parts.append(f"Code group: {tour_code}")
    if travel_date:
        remark_parts.append(f"Date: {travel_date}")
    remark_parts.append("")
    remark_parts.append("\n\n".join(formatted_desc_lines))
    remark_parts.append("")
    remark_parts.append(f"***Total: {total_amount:,.0f} {currency}")
    remark = "\n".join(remark_parts)

    if rows_for_form:
        rows_for_form[0]["remark"] = remark

    payment_date = datetime.now().strftime("%d/%m/%Y")
    date_from, date_to = _build_date_range(depart_date)

    _progress(f"{len(line_items)} expense line items: {rows_description}")

    try:
        # Navigate to the create form
        _progress("navigating to charges form...")
        nav = await browser_tools.navigate_to_charges_form(session_id=session_id)
        if nav["status"] != "success":
            if "session expired" in nav.get("message", "").lower() or "login" in nav.get("message", "").lower():
                _progress("session expired, re-authenticating...")
                relogin = await browser_tools.login(
                    username=website_username, password=website_password, session_id=session_id,
                )
                if relogin["status"] == "success":
                    nav = await browser_tools.navigate_to_charges_form(session_id=session_id)
            if nav["status"] != "success":
                return {"tour_code": tour_code, "status": "failed", "error": f"Navigation: {nav['message']}"}
        _progress("on charges form page")

        # Set date range and select program + tour code
        _progress(f"selecting program `{program_code}` and tour code...")
        sel = await browser_tools.select_program_and_tour(
            program_name=program_code,
            tour_code=tour_code,
            date_from=date_from,
            date_to=date_to,
            session_id=session_id,
        )
        if sel["status"] != "success":
            logger.warning("Program selection returned: %s -- continuing anyway", sel.get("message"))
        _progress("program selected")

        # Fill section 1 — multiple expense rows
        _progress(f"filling {len(rows_for_form)} expense row(s)...")
        fill = await browser_tools.fill_expense_rows(
            rows=rows_for_form,
            payment_date=payment_date,
            session_id=session_id,
        )
        if fill["status"] != "success":
            return {"tour_code": tour_code, "status": "failed", "error": f"Form fill: {fill['message']}"}
        _progress(f"expense rows filled: {len(fill.get('rows_filled', []))} items")

        # Click "+ เพิ่มในค่าใช้จ่ายบริษัท" to reveal section 2
        _progress("opening company expense section...")
        add_btn = await browser_tools.click_add_company_expense(session_id=session_id)
        if add_btn["status"] != "success":
            logger.warning("Could not open company expense section: %s", add_btn.get("message"))

        # Determine primary charge type for company expense section.
        # If expense_type was selected by the user, use it for the
        # payment_type dropdown; otherwise fall back to the first item's type.
        EXPENSE_TYPE_TO_CHARGE = {
            "flight": "flight",
            "land_tour": "land_tour",
            "insurance": "insurance",
            "misc": "other",
        }
        primary_charge_type = (
            EXPENSE_TYPE_TO_CHARGE.get(expense_type)
            or line_items[0].get("charge_type", "other")
        )

        # Build a structured company remark: Supplier, Company, Code Group, expenses, total
        company_remark_parts = []
        if supplier_name:
            company_remark_parts.append(f"Supplier: {supplier_name}")
        if company_name:
            company_remark_parts.append(f"Company: {company_name}")
        if tour_code:
            company_remark_parts.append(f"Code group: {tour_code}")
        if program_code:
            company_remark_parts.append(f"Program: {program_code}")
        company_remark_parts.append("")
        company_remark_parts.append("\n\n".join(formatted_desc_lines))
        company_remark_parts.append("")
        company_remark_parts.append(f"***Total: {total_amount:,.0f} {currency}")
        company_remark = "\n".join(company_remark_parts)

        _progress("filling company expense section...")
        comp_fill = await browser_tools.fill_company_expense(
            company_name=company_name,
            payment_method="โอนเข้าบัญชี",
            supplier_name=supplier_name,
            amount=total_amount,
            payment_date=payment_date,
            payment_type=PAYMENT_TYPE_MAP.get(primary_charge_type, "ค่าทัวร์/ค่าแลนด์"),
            period=tour_code,
            remark=company_remark,
            session_id=session_id,
        )
        if comp_fill["status"] != "success":
            logger.warning("Company expense fill issue: %s", comp_fill.get("message"))

        # Submit
        _progress("submitting form...")
        sub = await browser_tools.submit_form(session_id=session_id)
        if sub["status"] != "success":
            return {"tour_code": tour_code, "status": "failed", "error": f"Submit: {sub['message']}"}

        # Extract the expense number
        _progress("extracting order number...")
        ext = await browser_tools.extract_order_number(session_id=session_id)
        expense_number = ext.get("expense_number", "UNKNOWN")

        # Navigate to the manage page to finalize company & supplier
        _progress("navigating to expense manage page...")
        try:
            manage_nav = await asyncio.wait_for(
                browser_tools.navigate_to_manage_page(session_id=session_id),
                timeout=30,
            )
            if manage_nav["status"] == "success":
                _progress(f"on manage page (expense {manage_nav.get('expense_id', '')}), "
                           f"selecting company and filling supplier...")
                manage_fill = await asyncio.wait_for(
                    browser_tools.fill_manage_page_details(
                        company_name=company_name,
                        supplier_name=supplier_name,
                        session_id=session_id,
                    ),
                    timeout=30,
                )
                if manage_fill["status"] == "success":
                    _progress("manage page updated successfully")
                else:
                    logger.warning("Manage page fill issue: %s", manage_fill.get("message"))
                    _progress(f"manage page: {manage_fill.get('message', 'partial')}")
            else:
                logger.warning("Could not navigate to manage page: %s", manage_nav.get("message"))
                _progress("manage page link not found (expense still created)")
        except (asyncio.TimeoutError, Exception) as manage_err:
            logger.warning("Manage page step timed out or failed: %s (expense still created)", manage_err)
            _progress("manage page step skipped (expense still created)")

        return {
            "tour_code": tour_code,
            "program_code": program_code,
            "supplier_name": supplier_name,
            "total_amount": total_amount,
            "currency": currency,
            "line_items": len(line_items),
            "rows_description": rows_description,
            "depart_date": depart_date,
            "status": "success",
            "expense_number": expense_number,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error("Expense failed for %s: %s", tour_code, e, exc_info=True)
        # Log timeout-specific learning
        err_str = str(e)
        if "Timed out" in err_str or "timeout" in err_str.lower():
            learning_service.log_learning(
                agent="Accounting Agent",
                category="best_practice",
                summary=f"Browser operation timed out for {tour_code}",
                details=f"Error: {err_str}. The form interaction took too long, "
                        f"likely due to AJAX loading or overlay blocking elements.",
                suggested_action="Increase timeout or add page.wait_for_load_state() before form interaction",
                priority="high",
                tags=["timeout", "browser", "form_filling"],
                related_files=["tools/browser_tools.py"],
            )
        learning_service.log_error(
            agent="Accounting Agent",
            error_type="expense_processing",
            summary=f"Expense processing failed for tour group {tour_code}",
            error_message=str(e),
            context=f"Tour code: {tour_code}, Items: {len(line_items)}, Currency: {currency}",
            suggested_fix="Check browser form selectors and page state after AJAX operations",
            related_files=["services/expense_service.py", "tools/browser_tools.py"],
        )
        return {
            "tour_code": tour_code,
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


def _format_expense_description(
    expense_label: str,
    travel_date: str = None,
    travel_date_start: str = None,
    travel_date_end: str = None,
    pax: int = None,
    unit_price: float = None,
    quantity: int = None,
    amount: float = 0,
    currency: str = "THB",
    tour_code: str = None,
    calculation_note: str = None,
) -> str:
    """
    Build a human-readable expense description block.

    Output format:
        Payment = Airline Ticket
        Date : 04-09 Mar 2026
        Pax = 21
        Price = 6,200 THB
        Total = 21 x 6,200 = 130,200 THB
    """
    lines = []
    lines.append(f"Payment = {expense_label}")

    date_str = _format_travel_date(travel_date, travel_date_start, travel_date_end, tour_code=tour_code)
    if date_str:
        lines.append(f"Date : {date_str}")

    if pax:
        lines.append(f"Pax = {pax}")

    if unit_price:
        lines.append(f"Price = {unit_price:,.0f} {currency}")

    if calculation_note:
        lines.append(f"Total = {calculation_note} {currency}")
    elif pax and unit_price and quantity and quantity > 1:
        lines.append(f"Total = {unit_price:,.0f} x {pax} pax x {quantity} = {amount:,.0f} {currency}")
    elif pax and unit_price:
        lines.append(f"Total = {pax} x {unit_price:,.0f} = {amount:,.0f} {currency}")
    elif amount:
        lines.append(f"Total = {amount:,.0f} {currency}")

    return "\n".join(lines)


def _format_travel_date(
    travel_date: str = None,
    travel_date_start: str = None,
    travel_date_end: str = None,
    tour_code: str = None,
) -> str:
    """
    Format travel dates into a human-readable string like '04-09 Mar 2026'.

    Priority:
    1. Structured start/end dates (dd/mm/yyyy)
    2. Raw travel_date in mmdd-mmdd format (e.g., "0304-0309")
    3. Raw travel_date as-is
    """
    MONTHS = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
    }

    # Strategy 1: structured start/end dates
    if travel_date_start and travel_date_end:
        try:
            start = datetime.strptime(travel_date_start, "%d/%m/%Y")
            end = datetime.strptime(travel_date_end, "%d/%m/%Y")
            if start.month == end.month and start.year == end.year:
                return f"{start.day:02d}-{end.day:02d} {MONTHS[start.month]} {start.year}"
            else:
                return (
                    f"{start.day:02d} {MONTHS[start.month]} - "
                    f"{end.day:02d} {MONTHS[end.month]} {end.year}"
                )
        except (ValueError, KeyError):
            pass

    if travel_date_start:
        try:
            start = datetime.strptime(travel_date_start, "%d/%m/%Y")
            return f"{start.day:02d} {MONTHS[start.month]} {start.year}"
        except (ValueError, KeyError):
            pass

    # Strategy 2: parse mmdd-mmdd format (e.g., "0304-0309")
    if travel_date:
        mmdd_match = re.match(r'^(\d{4})-(\d{4})$', travel_date.strip())
        if mmdd_match:
            raw_start, raw_end = mmdd_match.group(1), mmdd_match.group(2)
            try:
                sm, sd = int(raw_start[:2]), int(raw_start[2:])
                em, ed = int(raw_end[:2]), int(raw_end[2:])
                if 1 <= sm <= 12 and 1 <= sd <= 31 and 1 <= em <= 12 and 1 <= ed <= 31:
                    year = _extract_year_from_tour_code(tour_code)
                    year_str = f" {year}" if year else ""
                    if sm == em:
                        return f"{sd:02d}-{ed:02d} {MONTHS[sm]}{year_str}"
                    else:
                        return f"{sd:02d} {MONTHS[sm]} - {ed:02d} {MONTHS[em]}{year_str}"
            except (ValueError, KeyError):
                pass

    return travel_date or ""


def _extract_year_from_tour_code(tour_code: str) -> int | None:
    """Extract the year from a tour code's embedded yymmdd date."""
    if not tour_code or len(tour_code) < 6:
        return None
    stripped = tour_code.strip().rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
    if len(stripped) < 6:
        return None
    tail = stripped[-6:]
    if tail.isdigit():
        yy = int(tail[:2])
        mm = int(tail[2:4])
        if 1 <= mm <= 12 and 20 <= yy <= 40:
            return 2000 + yy
    return None


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


def process_single_expense_api(data: dict, session_id: str = "default") -> dict:
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

    tour_code = record["tour_code"]
    result = run_in_thread(_process_tour_group(tour_code, [record], session_id=session_id))
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _write_results_csv(csv_path: str, results: list, job_id: str):
    """Write processing results to a CSV file for export."""
    import csv
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Job ID",
            "Tour Code",
            "Program Code",
            "Supplier",
            "Line Items",
            "Total Amount",
            "Currency",
            "Departure Date",
            "Order Number",
            "Status",
            "Error",
            "Timestamp",
        ])
        for r in results:
            writer.writerow([
                job_id,
                r.get("tour_code", ""),
                r.get("program_code", ""),
                r.get("supplier_name", ""),
                r.get("rows_description", ""),
                r.get("total_amount", ""),
                r.get("currency", "THB"),
                r.get("depart_date", ""),
                r.get("expense_number", ""),
                r.get("status", ""),
                r.get("error", ""),
                r.get("timestamp", ""),
            ])
    logger.info("CSV report saved: %s", csv_path)


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
        except Exception:
            pass


def _emit_timed(emit_fn, job_start: datetime, agent: str, message: str):
    """Emit a progress message with timestamp and elapsed duration."""
    now = datetime.now()
    elapsed = (now - job_start).total_seconds()
    timestamp = now.strftime("%H:%M:%S")
    _emit(emit_fn, "agent_progress", {
        "agent": agent,
        "message": f"[{timestamp} | +{elapsed:.0f}s] {message}",
    })


def _group_records_by_tour(records: list, expense_type: str = "") -> dict:
    """Smart grouping of parsed records into expense orders.

    Grouping behavior depends on `expense_type`:
    - "land_tour" (Tour fare): Combine all items with the same tour code
      into ONE expense form (tour fare + supplement + guide tip + add-on).
    - "flight" / "insurance" / "misc": Each line item becomes its OWN
      separate expense order, even if they share a tour code.
    - "" (empty / unset): Falls back to "land_tour" behaviour (combine
      by tour code) for backwards compatibility.

    Returns: { canonical_tour_code: [record, ...], ... }
    """
    from collections import OrderedDict

    # ── Split mode: each record = its own expense order ──
    split_types = {"flight", "insurance", "misc"}
    if expense_type in split_types:
        grouped: dict[str, list] = OrderedDict()
        for i, rec in enumerate(records):
            tc = rec.get("tour_code", "UNKNOWN")
            key = f"{tc}__item{i}" if tc in grouped or any(
                k.startswith(tc) for k in grouped
            ) else tc
            # Use a unique key per record to prevent merging
            unique_key = f"{tc}__item{i}"
            grouped[unique_key] = [rec]

        logger.info(
            "Split grouping (expense_type=%s): %d records → %d separate orders",
            expense_type, len(records), len(grouped),
        )
        return grouped

    # ── Combine mode (land_tour / default): group by normalized tour code ──
    def _normalize_tour_code(tc: str) -> str:
        tc = tc.strip().upper()
        if tc and tc[-1].isalpha() and len(tc) > 6:
            base = tc.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
            if len(base) >= 6 and base[-1].isdigit():
                return base
        return tc

    norm_to_canonical: dict[str, str] = {}
    grouped = OrderedDict()

    for rec in records:
        tc_raw = rec.get("tour_code", "UNKNOWN")
        tc_norm = _normalize_tour_code(tc_raw)

        if tc_norm in norm_to_canonical:
            canonical = norm_to_canonical[tc_norm]
        else:
            canonical = tc_raw
            norm_to_canonical[tc_norm] = canonical

        grouped.setdefault(canonical, []).append(rec)

    # Pass 2: merge groups that share the same program_code
    pc_to_group: dict[str, str] = {}
    merge_map: dict[str, str] = {}

    for canonical, items in grouped.items():
        for item in items:
            pc = (item.get("program_code") or "").strip().upper()
            if not pc:
                continue
            if pc in pc_to_group and pc_to_group[pc] != canonical:
                merge_map[canonical] = pc_to_group[pc]
            else:
                pc_to_group[pc] = canonical

    if merge_map:
        merged: dict[str, list] = OrderedDict()
        for canonical, items in grouped.items():
            target = merge_map.get(canonical, canonical)
            merged.setdefault(target, []).extend(items)
        grouped = merged

    if len(grouped) < len(records):
        for tc, items in grouped.items():
            types = ", ".join(i.get("charge_type", "?") for i in items)
            logger.info(
                "Grouped %d line items under '%s': [%s]",
                len(items), tc, types,
            )

    return grouped


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
        cur = record.get("currency", "THB")
        parts.append(f"amount=`{record['amount']:,.0f} {cur}`")
    if record.get("charge_type"):
        parts.append(f"type=`{record['charge_type']}`")
    return ", ".join(parts) if parts else "basic fields detected"

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
from services import learning_service
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
    grouped = _group_records_by_tour(records)

    grand_total = sum(r.get("amount", 0) for r in records)
    primary_currency = detected_currency or records[0].get("currency", "THB")

    group_lines = []
    for tc, items in grouped.items():
        subtotal = sum(r.get("amount", 0) for r in items)
        item_labels = ", ".join(r.get("description", "?")[:20] for r in items)
        group_lines.append(
            f"- `{tc}`: {len(items)} item{'s' if len(items) > 1 else ''} "
            f"= **{subtotal:,.0f} {primary_currency}** ({item_labels})"
        )
    group_summary = "\n".join(group_lines)

    _emit_timed(emit_fn, job_start, "Document Parser",
                f"**Step 2/7:** Extracted **{len(records)}** expense line items "
                f"across **{len(grouped)}** tour groups.{currency_note}\n"
                f"**Grand Total: {grand_total:,.0f} {primary_currency}**\n"
                f"{group_summary}\n"
                f"Fields classified: {_describe_fields(records[0])}")

    # Save parsed data
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    parsed_path = os.path.join(Config.DATA_DIR, f"parsed_{job_id}.json")
    with open(parsed_path, "w", encoding="utf-8") as f:
        json.dump({"job_id": job_id, "records": records, "parse_info": parse_result}, f, ensure_ascii=False, indent=2)

    # ── Decide: n8n or direct ──
    if n8n_integration.is_n8n_enabled():
        return _run_via_n8n(job_id, records, emit_fn)
    else:
        return _run_direct(job_id, grouped, emit_fn)


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


def _run_direct(job_id: str, grouped_records: dict, emit_fn) -> dict:
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
    coro = _run_direct_async(job_id, grouped_records, thread_safe_emit)

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


async def _run_direct_async(job_id: str, grouped_records: dict, emit_fn) -> dict:
    """Async implementation of the direct expense automation flow.

    grouped_records: { tour_code: [record, ...], ... }

    NOTE: emit_fn here is the thread-safe queue wrapper, NOT the real
    SocketIO emit.  Safe to call from the Playwright OS thread.
    """

    job_start = datetime.now()

    _emit_timed(emit_fn, job_start, "Accounting Agent", "Logging in...")
    login_result = await browser_tools.login()
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

    for i, (tour_code, line_items) in enumerate(grouped_records.items(), 1):
        record_start = datetime.now()
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
                _process_tour_group(tour_code, line_items, emit_fn, job_start),
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

    # Close browser
    _emit_timed(emit_fn, job_start, "Accounting Agent", "Closing browser...")
    await browser_tools.close_browser()

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
    "insurance": "ค่าทัวร์/ค่าแลนด์",
    "entrance_fee": "ค่าทัวร์/ค่าแลนด์",
    "other": "ค่าทัวร์/ค่าแลนด์",
}

CHARGE_TYPE_LABELS = {
    "flight": "Flight",
    "land_tour": "Tour Fare",
    "single_supplement": "Single Supplement",
    "service_fee": "Service Fee",
    "guide_tip": "Guide/Tips",
    "visa": "Visa",
    "accommodation": "Accommodation",
    "meal": "Meals",
    "transport": "Transport",
    "insurance": "Insurance",
    "entrance_fee": "Entrance Fee",
    "other": "Other",
}


async def _process_tour_group(
    tour_code: str, line_items: list, emit_fn=None, job_start=None
) -> dict:
    """Process a tour group (one or more line items) through a single form submission."""
    _job_start = job_start or datetime.now()

    def _progress(msg):
        _emit_timed(emit_fn, _job_start, "Accounting Agent", f"`{tour_code}` {msg}")

    first = line_items[0]
    supplier_name_raw = first.get("supplier_name", "")
    travel_date = first.get("travel_date", "")
    program_code = first.get("program_code", "")
    company_name = first.get("company_name", "")
    currency = first.get("currency", "THB")
    exchange_rate = first.get("exchange_rate", 1.0)

    total_amount = sum(r.get("amount", 0) for r in line_items)

    # ── Step A: Translate supplier name ──
    _progress("translating supplier name...")
    supplier_name = translate_supplier_name(supplier_name_raw)

    # ── Step B: Extract departure date from tour code ──
    depart_date = browser_tools.extract_date_from_tour_code(tour_code)
    if depart_date:
        logger.info("Departure date from tour code %s: %s", tour_code, depart_date)
    else:
        logger.info("No embedded date in tour code %s, using travel_date field", tour_code)

    # ── Step C: Look up program code on /travelpackage ──
    if not program_code:
        _progress("searching program code on /travelpackage...")
        lookup = await browser_tools.search_program_code(tour_code)
        if lookup["status"] == "success":
            program_code = lookup["program_code"]
            _progress(f"found program: `{program_code}`")
        else:
            _progress("program code not found, continuing...")
            logger.warning("Program code lookup failed: %s", lookup.get("message"))

    # Build expense rows for multi-line form filling
    rows_for_form = []
    rows_description_parts = []
    for item in line_items:
        desc = item.get("description", "")
        ct = item.get("charge_type", "other")
        amt = item.get("amount", 0)
        pax = item.get("pax")
        up = item.get("unit_price")

        if not up and amt and pax:
            up = round(amt / pax)

        label = CHARGE_TYPE_LABELS.get(ct, ct)
        rows_description_parts.append(f"{label}: {amt:,.0f} {currency}")

        rows_for_form.append({
            "description": desc,
            "charge_type": ct,
            "amount": amt,
            "currency": currency,
            "exchange_rate": exchange_rate,
            "pax": pax,
            "unit_price": up,
        })

    rows_description = " | ".join(rows_description_parts)

    # Build remark
    remark_parts = []
    if supplier_name:
        remark_parts.append(supplier_name)
    remark_parts.append(f"Code group: {tour_code}")
    if travel_date:
        remark_parts.append(f"Date: {travel_date}")
    for item in line_items:
        label = CHARGE_TYPE_LABELS.get(item.get("charge_type", ""), item.get("charge_type", ""))
        remark_parts.append(f"{label}: {item.get('amount', 0):,.0f} {currency}")
    remark = "\n".join(remark_parts)

    if rows_for_form:
        rows_for_form[0]["remark"] = remark

    payment_date = datetime.now().strftime("%d/%m/%Y")
    date_from, date_to = _build_date_range(depart_date)

    _progress(f"{len(line_items)} expense line items: {rows_description}")

    try:
        # Navigate to the create form
        _progress("navigating to charges form...")
        nav = await browser_tools.navigate_to_charges_form()
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
        )
        if sel["status"] != "success":
            logger.warning("Program selection returned: %s -- continuing anyway", sel.get("message"))
        _progress("program selected")

        # Fill section 1 — multiple expense rows
        _progress(f"filling {len(rows_for_form)} expense row(s)...")
        fill = await browser_tools.fill_expense_rows(
            rows=rows_for_form,
            payment_date=payment_date,
        )
        if fill["status"] != "success":
            return {"tour_code": tour_code, "status": "failed", "error": f"Form fill: {fill['message']}"}
        _progress(f"expense rows filled: {len(fill.get('rows_filled', []))} items")

        # Click "+ เพิ่มในค่าใช้จ่ายบริษัท" to reveal section 2
        _progress("opening company expense section...")
        add_btn = await browser_tools.click_add_company_expense()
        if add_btn["status"] != "success":
            logger.warning("Could not open company expense section: %s", add_btn.get("message"))

        # Determine primary charge type for company expense section
        primary_charge_type = line_items[0].get("charge_type", "other")

        company_remark_parts = []
        if tour_code:
            company_remark_parts.append(tour_code)
        if program_code:
            company_remark_parts.append(program_code)

        _progress("filling company expense section...")
        comp_fill = await browser_tools.fill_company_expense(
            company_name=company_name,
            payment_method="โอนเข้าบัญชี",
            supplier_name=supplier_name,
            amount=total_amount,
            payment_date=payment_date,
            payment_type=PAYMENT_TYPE_MAP.get(primary_charge_type, "ค่าทัวร์/ค่าแลนด์"),
            period=tour_code,
            remark=" / ".join(company_remark_parts),
        )
        if comp_fill["status"] != "success":
            logger.warning("Company expense fill issue: %s", comp_fill.get("message"))

        # Submit
        _progress("submitting form...")
        sub = await browser_tools.submit_form()
        if sub["status"] != "success":
            return {"tour_code": tour_code, "status": "failed", "error": f"Submit: {sub['message']}"}

        # Extract the expense number
        _progress("extracting order number...")
        ext = await browser_tools.extract_order_number()

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
            "expense_number": ext.get("expense_number", "UNKNOWN"),
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

    tour_code = record["tour_code"]
    result = run_in_thread(_process_tour_group(tour_code, [record]))
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


def _group_records_by_tour(records: list) -> dict:
    """Group parsed records by tour_code.

    When an invoice has multiple line items for the same tour group
    (e.g. tour fare, single supplement, tips), they share the same
    tour_code and should be submitted as multiple expense rows in a
    single form.

    Returns: { tour_code: [record, ...], ... }  (preserving order)
    """
    from collections import OrderedDict
    grouped: dict[str, list] = OrderedDict()
    for rec in records:
        tc = rec.get("tour_code", "UNKNOWN")
        grouped.setdefault(tc, []).append(rec)
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

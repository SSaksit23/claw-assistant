"""
Accounting Agent -- Financial Operations Specialist.

Automates expense recording on the QualityB2BPackage website.
Processes CSV data or individual expense entries and submits them
through the charges_group/create form.
"""

import logging
from datetime import datetime

from tools.browser_manager import run_async
from tools import browser_tools
from tools.data_tools import load_csv, validate_expense_data

from config import Config

logger = logging.getLogger(__name__)


async def _process_single_expense(record: dict, emit_fn=None) -> dict:
    """Process a single expense record through the website form."""
    tour_code = record.get("tour_code", "")
    amount = record.get("amount", 0)
    description = record.get("description", tour_code)
    charge_type = record.get("charge_type", "other")
    currency = record.get("currency", "THB")
    exchange_rate = record.get("exchange_rate", 1.0)
    payment_date = record.get("payment_date", datetime.now().strftime("%d/%m/%Y"))
    program_code = record.get("program_code", "")

    logger.info(f"Processing expense: {tour_code}, {amount} {currency}")

    try:
        # Step 1: Navigate to form
        nav_result = await browser_tools.navigate_to_charges_form()
        if nav_result["status"] != "success":
            return {
                "tour_code": tour_code,
                "status": "failed",
                "error": f"Navigation failed: {nav_result['message']}",
            }

        # Step 2: Select program and tour
        select_result = await browser_tools.select_program_and_tour(
            program_name=program_code,
            tour_code=tour_code,
        )
        if select_result["status"] != "success":
            return {
                "tour_code": tour_code,
                "status": "failed",
                "error": f"Selection failed: {select_result['message']}",
            }

        # Step 3: Fill expense form
        fill_result = await browser_tools.fill_expense_form(
            payment_date=payment_date,
            description=description,
            charge_type=charge_type,
            amount=amount,
            currency=currency,
            exchange_rate=exchange_rate,
        )
        if fill_result["status"] != "success":
            return {
                "tour_code": tour_code,
                "status": "failed",
                "error": f"Form fill failed: {fill_result['message']}",
            }

        # Step 4: Submit form
        submit_result = await browser_tools.submit_form()
        if submit_result["status"] != "success":
            return {
                "tour_code": tour_code,
                "status": "failed",
                "error": f"Submit failed: {submit_result['message']}",
            }

        # Step 5: Extract order number
        extract_result = await browser_tools.extract_order_number()

        return {
            "tour_code": tour_code,
            "program_code": program_code,
            "amount": amount,
            "currency": currency,
            "status": "success",
            "expense_number": extract_result.get("expense_number", "UNKNOWN"),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Expense processing failed for {tour_code}: {e}", exc_info=True)
        return {
            "tour_code": tour_code,
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


async def _run_expense_automation(records: list, emit_fn=None) -> dict:
    """Run the full expense automation workflow for multiple records."""
    results = []
    success_count = 0
    fail_count = 0

    # Step 1: Login
    if emit_fn:
        emit_fn("agent_progress", {
            "agent": "Accounting Agent",
            "message": "Logging into qualityb2bpackage.com...",
        })

    login_result = await browser_tools.login()
    if login_result["status"] != "success":
        return {
            "content": f"Login failed: {login_result['message']}. Cannot process expenses.",
            "data": {"status": "failed", "results": []},
        }

    # Step 2: Process each record
    total = len(records)
    for i, record in enumerate(records, 1):
        if emit_fn:
            emit_fn("agent_progress", {
                "agent": "Accounting Agent",
                "message": f"Processing expense {i}/{total}: {record.get('tour_code', 'N/A')}...",
            })

        result = await _process_single_expense(record, emit_fn)
        results.append(result)

        if result["status"] == "success":
            success_count += 1
        else:
            fail_count += 1

    # Browser stays alive for session reuse; idle timeout handles cleanup

    # Build summary
    summary = f"**Expense Processing Complete**\n\n"
    summary += f"- Total records: {total}\n"
    summary += f"- Successful: {success_count}\n"
    summary += f"- Failed: {fail_count}\n\n"

    if success_count > 0:
        summary += "**Successful entries:**\n"
        for r in results:
            if r["status"] == "success":
                summary += f"- `{r['tour_code']}`: {r['amount']} {r.get('currency', 'THB')} -> Expense #{r.get('expense_number', 'N/A')}\n"

    if fail_count > 0:
        summary += "\n**Failed entries:**\n"
        for r in results:
            if r["status"] != "success":
                summary += f"- `{r['tour_code']}`: {r.get('error', 'Unknown error')}\n"

    return {
        "content": summary,
        "data": {
            "status": "completed",
            "total": total,
            "success_count": success_count,
            "fail_count": fail_count,
            "results": results,
        },
    }


def handle_expense_task(task_details: dict, file_path: str = None, emit_fn=None) -> dict:
    """
    Entry point called by the Assignment Agent.

    Handles:
    - CSV file processing
    - Single expense entry from chat
    """
    records = []

    # If a file was uploaded, load it
    if file_path:
        if emit_fn:
            emit_fn("agent_progress", {
                "agent": "Accounting Agent",
                "message": f"Loading file: {file_path}...",
            })

        df = load_csv(file_path)
        if df is None:
            return {
                "content": f"Failed to load file: {file_path}. Please check the file format.",
                "data": None,
            }

        validation = validate_expense_data(df)
        if validation["valid_count"] == 0:
            error_summary = "\n".join(
                f"- Row {e['row']}: {', '.join(e['errors'])}"
                for e in validation["errors"][:5]
            )
            return {
                "content": f"No valid records found in the file.\n\n**Errors:**\n{error_summary}",
                "data": validation,
            }

        records = validation["records"]

        if emit_fn:
            emit_fn("agent_progress", {
                "agent": "Accounting Agent",
                "message": f"Found {validation['valid_count']} valid records ({validation['invalid_count']} invalid).",
            })

    else:
        # Single entry from task details
        params = task_details.get("parameters", {})
        if params.get("tour_code") and params.get("amount"):
            records = [params]
        else:
            return {
                "content": (
                    "I need expense data to process. You can:\n"
                    "1. Upload a CSV file with tour_code and amount columns\n"
                    "2. Provide details like: 'Record expense for tour BTMYSP16N240107, amount 1000 THB'"
                ),
                "data": None,
            }

    # Run the automation
    result = run_async(_run_expense_automation(records, emit_fn))
    return result

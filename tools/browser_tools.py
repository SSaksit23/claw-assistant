"""
Browser automation tools for interacting with qualityb2bpackage.com.

Each tool is an async function that operates on the shared BrowserManager page.
These are wrapped as CrewAI-compatible tools in the agent definitions.
"""

import re
import logging
import asyncio
from datetime import datetime

from tools.browser_manager import BrowserManager
from config import Config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool 1: LoginTool
# ---------------------------------------------------------------------------
async def login(username: str = None, password: str = None, max_retries: int = 3) -> dict:
    """
    Authenticate with the QualityB2BPackage website.
    Retries with exponential backoff on failure.
    """
    manager = BrowserManager.get_instance()
    if manager.is_logged_in:
        return {"status": "success", "message": "Already logged in"}

    username = username or Config.WEBSITE_USERNAME
    password = password or Config.WEBSITE_PASSWORD
    page = await manager.get_page()

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Login attempt {attempt}/{max_retries}")
            await page.goto(Config.WEBSITE_URL, wait_until="networkidle")
            await asyncio.sleep(1)

            # Fill login form
            await page.fill('input[name="username"], input[name="email"], #username, #email', username)
            await page.fill('input[name="password"], #password', password)

            # Click submit
            await page.click('button[type="submit"], input[type="submit"], .btn-login, .login-btn')
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            # Verify login by checking URL change or dashboard element
            current_url = page.url
            if "login" not in current_url.lower() or "dashboard" in current_url.lower():
                manager.is_logged_in = True
                await manager.screenshot("login_success")
                logger.info("Login successful")
                return {"status": "success", "message": "Logged in successfully"}

            logger.warning(f"Login may have failed, URL: {current_url}")

        except Exception as e:
            logger.error(f"Login attempt {attempt} failed: {e}")
            if attempt < max_retries:
                wait_time = Config.RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.info(f"Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)

    await manager.screenshot("login_failed")
    return {"status": "failed", "message": "Login failed after all retries"}


# ---------------------------------------------------------------------------
# Tool 2: NavigateToChargesFormTool
# ---------------------------------------------------------------------------
async def navigate_to_charges_form() -> dict:
    """Navigate to the charges/expenses creation form."""
    manager = BrowserManager.get_instance()
    page = await manager.get_page()

    try:
        url = Config.CHARGES_FORM_URL
        logger.info(f"Navigating to charges form: {url}")
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(2)

        # Verify we're on the right page
        title = await page.title()
        await manager.screenshot("charges_form_loaded")

        return {"status": "success", "message": f"Navigated to charges form", "title": title}

    except Exception as e:
        logger.error(f"Navigation failed: {e}")
        await manager.screenshot("navigation_failed")
        return {"status": "failed", "message": str(e)}


# ---------------------------------------------------------------------------
# Tool 3: SelectProgramAndTourTool
# ---------------------------------------------------------------------------
async def select_program_and_tour(
    program_name: str = None,
    tour_code: str = None,
    date_from: str = None,
    date_to: str = None,
) -> dict:
    """
    Select the travel program and tour code on the charges form.
    Uses JavaScript injection to handle Bootstrap selectpicker dropdowns.
    """
    manager = BrowserManager.get_instance()
    page = await manager.get_page()

    try:
        # Set date range if provided (defaults to broad range)
        if date_from:
            await _set_date_field(page, "program_date_from", date_from)
        if date_to:
            await _set_date_field(page, "program_date_to", date_to)

        # Select program using Bootstrap selectpicker JS injection
        if program_name:
            await _select_bootstrap_dropdown(page, "program_id", program_name)
            await asyncio.sleep(1)

        # Select tour code
        if tour_code:
            await _select_bootstrap_dropdown(page, "tour_code", tour_code)
            await asyncio.sleep(1)

        await manager.screenshot("program_selected")
        return {
            "status": "success",
            "message": f"Selected program: {program_name}, tour: {tour_code}",
        }

    except Exception as e:
        logger.error(f"Program/tour selection failed: {e}")
        await manager.screenshot("selection_failed")
        return {"status": "failed", "message": str(e)}


# ---------------------------------------------------------------------------
# Tool 4: FillExpenseFormTool
# ---------------------------------------------------------------------------
async def fill_expense_form(
    payment_date: str = None,
    payment_time: str = None,
    receipt_date: str = None,
    receipt_number: str = "",
    description: str = "",
    charge_type: str = "other",
    amount: float = 0,
    currency: str = "THB",
    exchange_rate: float = 1.0,
) -> dict:
    """
    Fill a single expense row on the charges form.
    Handles date pickers, text inputs, and dropdown selectors.
    """
    manager = BrowserManager.get_instance()
    page = await manager.get_page()

    try:
        today = datetime.now().strftime("%d/%m/%Y")

        # Payment date
        await _set_date_field(page, "payment_date", payment_date or today)

        # Payment time (optional)
        if payment_time:
            await page.fill('[name="payment_time"], #payment_time', payment_time)

        # Receipt date
        await _set_date_field(page, "receipt_date", receipt_date or today)

        # Receipt number
        if receipt_number:
            await page.fill('[name="receipt_number"], #receipt_number', str(receipt_number))

        # Expense row fields
        # Description
        desc_selectors = [
            'input[name*="description"]',
            'input[name*="desc"]',
            'textarea[name*="description"]',
        ]
        for sel in desc_selectors:
            try:
                if await page.query_selector(sel):
                    await page.fill(sel, description)
                    break
            except Exception:
                continue

        # Charge type dropdown
        await _select_bootstrap_dropdown(page, "type", charge_type)

        # Amount
        amount_selectors = [
            'input[name*="amount"]',
            'input[name*="money"]',
            'input[type="number"]',
        ]
        for sel in amount_selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.fill(str(amount))
                    break
            except Exception:
                continue

        # Currency
        await _select_bootstrap_dropdown(page, "currency", currency)

        # Exchange rate
        if exchange_rate != 1.0:
            rate_selectors = ['input[name*="rate"]', 'input[name*="exchange"]']
            for sel in rate_selectors:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.fill(str(exchange_rate))
                        break
                except Exception:
                    continue

        await manager.screenshot("form_filled")
        return {
            "status": "success",
            "message": f"Form filled: {description}, {amount} {currency}",
        }

    except Exception as e:
        logger.error(f"Form filling failed: {e}")
        await manager.screenshot("form_fill_failed")
        return {"status": "failed", "message": str(e)}


# ---------------------------------------------------------------------------
# Tool 5: SubmitFormTool
# ---------------------------------------------------------------------------
async def submit_form() -> dict:
    """Click Save/Submit and wait for confirmation."""
    manager = BrowserManager.get_instance()
    page = await manager.get_page()

    try:
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Save")',
            'button:has-text("บันทึก")',
            '.btn-primary[type="submit"]',
            '.btn-success',
        ]

        clicked = False
        for sel in submit_selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            return {"status": "failed", "message": "Could not find submit button"}

        # Wait for navigation or confirmation
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        await manager.screenshot("form_submitted")

        return {"status": "success", "message": "Form submitted successfully"}

    except Exception as e:
        logger.error(f"Form submission failed: {e}")
        await manager.screenshot("submit_failed")
        return {"status": "failed", "message": str(e)}


# ---------------------------------------------------------------------------
# Tool 6: ExtractOrderNumberTool
# ---------------------------------------------------------------------------
async def extract_order_number() -> dict:
    """
    Parse the confirmation page for the expense/order number.
    Uses multiple strategies: CSS selectors, regex patterns, page text.
    """
    manager = BrowserManager.get_instance()
    page = await manager.get_page()

    try:
        page_content = await page.content()
        page_text = await page.inner_text("body")

        # Strategy 1: Look for expense number pattern C2026XX-XXXXXX
        pattern = r"C\d{6}-\d{6}"
        matches = re.findall(pattern, page_text)
        if matches:
            expense_no = matches[-1]
            logger.info(f"Extracted expense number (regex): {expense_no}")
            return {"status": "success", "expense_number": expense_no}

        # Strategy 2: Look for any order/reference number pattern
        patterns = [
            r"(?:order|expense|reference|เลขที่)[:\s]*([A-Z0-9\-]+)",
            r"(?:หมายเลข|เลข)[:\s]*([A-Z0-9\-]+)",
            r"([A-Z]\d{6}-\d{4,6})",
        ]
        for pat in patterns:
            matches = re.findall(pat, page_text, re.IGNORECASE)
            if matches:
                expense_no = matches[-1]
                logger.info(f"Extracted expense number (pattern): {expense_no}")
                return {"status": "success", "expense_number": expense_no}

        # Strategy 3: Check alert/success message
        success_selectors = [".alert-success", ".alert.alert-success", ".success-message"]
        for sel in success_selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    text = await el.inner_text()
                    logger.info(f"Success message found: {text[:100]}")
                    return {
                        "status": "success",
                        "expense_number": "UNKNOWN",
                        "message": text,
                    }
            except Exception:
                continue

        await manager.screenshot("extract_number_failed")
        return {
            "status": "partial",
            "expense_number": "UNKNOWN",
            "message": "Form submitted but could not extract expense number",
        }

    except Exception as e:
        logger.error(f"Order number extraction failed: {e}")
        return {"status": "failed", "message": str(e)}


# ---------------------------------------------------------------------------
# Tool 7: CloseBrowserTool
# ---------------------------------------------------------------------------
async def close_browser() -> dict:
    """Gracefully close the browser session."""
    try:
        manager = BrowserManager.get_instance()
        await manager.close()
        return {"status": "success", "message": "Browser closed"}
    except Exception as e:
        logger.error(f"Error closing browser: {e}")
        return {"status": "failed", "message": str(e)}


# ---------------------------------------------------------------------------
# Shared helper: scrape table data from current page
# ---------------------------------------------------------------------------
async def scrape_table_data(page=None) -> list:
    """Extract data from HTML tables on the current page."""
    if page is None:
        manager = BrowserManager.get_instance()
        page = await manager.get_page()

    try:
        tables = await page.query_selector_all("table")
        all_data = []

        for table in tables:
            headers = []
            header_cells = await table.query_selector_all("thead th, thead td")
            for cell in header_cells:
                text = (await cell.inner_text()).strip()
                headers.append(text)

            rows = await table.query_selector_all("tbody tr")
            for row in rows:
                cells = await row.query_selector_all("td")
                if cells and headers:
                    row_data = {}
                    for i, cell in enumerate(cells):
                        key = headers[i] if i < len(headers) else f"col_{i}"
                        row_data[key] = (await cell.inner_text()).strip()
                    all_data.append(row_data)

        return all_data

    except Exception as e:
        logger.error(f"Table scraping failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Internal helpers for form interaction
# ---------------------------------------------------------------------------
async def _set_date_field(page, field_name: str, date_value: str):
    """Set a date picker field using JavaScript injection."""
    selectors = [
        f'input[name="{field_name}"]',
        f'input[name*="{field_name}"]',
        f"#{field_name}",
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                await page.evaluate(
                    f"""(el) => {{
                        el.value = '{date_value}';
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}""",
                    el,
                )
                return
        except Exception:
            continue
    logger.warning(f"Could not set date field: {field_name}")


async def _select_bootstrap_dropdown(page, field_name: str, value: str):
    """
    Select a value from a Bootstrap selectpicker dropdown using JS injection.
    This is required because Bootstrap selectpicker hides the native <select>
    and uses a custom widget.
    """
    js_code = f"""
    (function() {{
        // Try to find the select element
        var selectors = [
            'select[name="{field_name}"]',
            'select[name*="{field_name}"]',
            'select#{field_name}'
        ];
        var selectEl = null;
        for (var i = 0; i < selectors.length; i++) {{
            selectEl = document.querySelector(selectors[i]);
            if (selectEl) break;
        }}
        if (!selectEl) return 'SELECT_NOT_FOUND';

        // Find matching option
        var options = selectEl.options;
        var targetValue = '{value}'.toLowerCase();
        var found = false;

        for (var j = 0; j < options.length; j++) {{
            var optText = options[j].text.toLowerCase();
            var optVal = options[j].value.toLowerCase();
            if (optText.includes(targetValue) || optVal.includes(targetValue) || targetValue.includes(optVal)) {{
                selectEl.value = options[j].value;
                found = true;
                break;
            }}
        }}

        if (!found && options.length > 1) {{
            // Fallback: select first non-empty option
            for (var k = 0; k < options.length; k++) {{
                if (options[k].value) {{
                    selectEl.value = options[k].value;
                    found = true;
                    break;
                }}
            }}
        }}

        // Trigger events for Bootstrap selectpicker
        selectEl.dispatchEvent(new Event('change', {{ bubbles: true }}));
        if (typeof $ !== 'undefined' && $.fn.selectpicker) {{
            $(selectEl).selectpicker('refresh');
        }}

        return found ? 'SELECTED' : 'OPTION_NOT_FOUND';
    }})();
    """
    try:
        result = await page.evaluate(js_code)
        if result == "SELECT_NOT_FOUND":
            logger.warning(f"Select element not found for: {field_name}")
        elif result == "OPTION_NOT_FOUND":
            logger.warning(f"Option '{value}' not found in: {field_name}")
        else:
            logger.debug(f"Selected '{value}' in '{field_name}'")
    except Exception as e:
        logger.warning(f"Dropdown selection failed for {field_name}: {e}")

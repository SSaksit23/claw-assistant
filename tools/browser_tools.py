"""
Browser automation tools for qualityb2bpackage.com.

Selectors are based on actual inspection of the website (Feb 2026):
- Login:  #btnLogin (type="button", JS-driven)
- Form:   /charges_group/create
  Section 1 -- Expense details:
  - Date range:    input[name="start"], input[name="end"]
  - Tour program:  select[name="package"]  (Bootstrap selectpicker)
  - Tour code:     select[name="period"]   (Bootstrap selectpicker)
  - Payment date:  input[name="payment_date"]
  - Description:   input[name="description[]"]
  - Type:          select[name="rate_type[]"]
  - Amount:        input[name="price[]"]
  - Currency:      #currency
  - Remark:        textarea[name="remark"]
  - Submit:        input[type="submit"][value="Save"]
  - Expense No.:   #charges_no  (read-only, auto-generated)

  Section 2 -- Company expense (after clicking a.addChargesCompany):
  - Company:       select[name="charges[id_company_charges_agent]"]  (selectpicker, 35 opts)
  - Payment method: select[name="charges[payment_type]"]  (selectpicker: โอนเข้าบัญชี/เช็ค/บัตรเครดิต)
  - Pay to:        input[name="pay_name"]  (supplier / land operator name)
  - Agent:         input[name="agent_name"]
  - Amount:        input[name="charges[amount]"]
  - Fee:           input[name="charges[fee]"]
  - Payment date:  input[name="charges[pay_date]"]
  - Payment type:  select[name="charges[id_company_charges_type]"]  (selectpicker, 56 opts)
  - Period:        input[name="charges[remark_period]"]
  - Remark:        textarea[name="charges[remark]"]
"""

import re
import logging
import asyncio
from datetime import datetime

from tools.browser_manager import BrowserManager
from config import Config

logger = logging.getLogger(__name__)

CHARGE_TYPE_MAP = {
    "flight": "ค่าตั๋วเครื่องบิน",
    "visa": "ค่าวีซ่า",
    "allowance": "เบี้ยเลี้ยง (ค่าจ้างมัคคุเทศก์และหัวหน้าทัวร์)",
    "taxi": "ค่าแท็กซี่หัวหน้าทัวร์",
    "meal": "ค่าตั๋วเครื่องบิน",
    "accommodation": "ค่าตั๋วเครื่องบิน",
    "tour_guide": "เบี้ยเลี้ยง (ค่าจ้างมัคคุเทศก์และหัวหน้าทัวร์)",
    "other": "ค่าตั๋วเครื่องบิน",
}


def extract_date_from_tour_code(tour_code: str) -> str | None:
    """
    Extract departure date from a tour code.

    Many tour codes embed the departure date as 6 consecutive digits in
    yymmdd format, optionally followed by a trailing letter suffix.
    Examples:
        GO1TAO5NTAOQW260304   → 260304 → 04/03/2026
        2UCKG3NCKG3U260310B   → 260310 → 10/03/2026  (trailing 'B')

    Returns dd/mm/yyyy or None if no valid date found.
    """
    if not tour_code or len(tour_code) < 6:
        return None

    # Strip trailing alphabetic characters (common suffix like B, C, etc.)
    stripped = tour_code.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
    if len(stripped) < 6:
        return None

    tail = stripped[-6:]
    if not tail.isdigit():
        return None

    yy, mm, dd = int(tail[:2]), int(tail[2:4]), int(tail[4:6])
    if mm < 1 or mm > 12 or dd < 1 or dd > 31:
        return None

    year = 2000 + yy
    try:
        dt = datetime(year, mm, dd)
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        return None


async def search_program_code(group_code: str) -> dict:
    """
    Look up the program code for a given group/tour code by searching on
    /travelpackage.

    The search tries the full group code first, then progressively shorter
    prefixes (first 10, 7, 5 characters) until a match is found.

    Returns {"status": "success", "program_code": "...", "program_name": "..."}
            or {"status": "not_found", ...}
    """
    manager = BrowserManager.get_instance()
    page = await manager.get_page()

    # Build candidate search terms: full code, then shorter prefixes
    candidates = [group_code]
    for length in (10, 7, 5):
        prefix = group_code[:length]
        if prefix not in candidates and len(prefix) >= 5:
            candidates.append(prefix)

    try:
        url = Config.TRAVEL_PACKAGE_URL
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        search_input = await page.query_selector('#input_search')
        if not search_input:
            return {"status": "failed", "message": "#input_search not found on travelpackage page"}

        for search_term in candidates:
            logger.info("Searching travelpackage with: '%s'", search_term)
            await search_input.fill("")
            await search_input.fill(search_term)

            go_btn = await page.query_selector('.btn-go')
            if go_btn:
                await go_btn.click()
            await asyncio.sleep(4)

            match = await _find_program_in_results(page, group_code)
            if match:
                await manager.screenshot("travelpackage_found")
                logger.info(
                    "Found program code %s for group %s (searched '%s')",
                    match["program_code"], group_code, search_term,
                )
                return {"status": "success", **match}

        await manager.screenshot("travelpackage_not_found")
        return {
            "status": "not_found",
            "message": f"No program code found for '{group_code}' (tried: {candidates})",
        }

    except Exception as e:
        logger.error("Program search failed: %s", e)
        return {"status": "failed", "message": str(e)}


async def _find_program_in_results(page, group_code: str) -> dict | None:
    """
    Scan travelpackage table rows for a program code in parentheses.

    Matching priority:
    1. Program code whose prefix AND airline suffix both appear in the group_code
       e.g. group_code='2UCKG3NCKG3U260310B', program='2UCKG-3U001' → prefix
       '2UCKG' matches start AND '3U' appears in the group_code.
    2. Program code whose prefix matches the group_code start.
    3. Any program code found in the results.
    """
    rows = await page.query_selector_all("table tbody tr")
    logger.info("Search returned %d rows", len(rows))

    gc_upper = group_code.upper()
    prefix_and_airline_match = None
    prefix_match = None
    any_match = None

    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) < 3:
            continue
        program_text = (await cells[2].inner_text()).strip()

        codes = re.findall(r'\(([A-Z0-9]+-[A-Z0-9]+)\)', program_text)
        if not codes:
            continue

        program_code = codes[-1]
        parts = program_code.split("-")
        prefix = parts[0]
        airline = re.match(r"([A-Z0-9]{2})", parts[1]) if len(parts) > 1 else None
        airline_code = airline.group(1) if airline else ""

        entry = {
            "program_code": program_code,
            "program_name": program_text[:200],
        }

        if gc_upper.startswith(prefix):
            if airline_code and airline_code in gc_upper:
                if not prefix_and_airline_match:
                    prefix_and_airline_match = entry
            elif not prefix_match:
                prefix_match = entry
        elif not any_match:
            any_match = entry

    result = prefix_and_airline_match or prefix_match or any_match
    if result:
        logger.info("Best program match: %s", result["program_code"])
    return result


async def login(username: str = None, password: str = None, max_retries: int = 3) -> dict:
    """
    Log in to qualityb2bpackage.com.
    The login button is #btnLogin (type="button", JS-driven).
    """
    manager = BrowserManager.get_instance()
    if manager.is_logged_in:
        return {"status": "success", "message": "Already logged in"}

    username = username or Config.WEBSITE_USERNAME
    password = password or Config.WEBSITE_PASSWORD
    page = await manager.get_page()

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Login attempt %d/%d", attempt, max_retries)
            await page.goto(Config.WEBSITE_URL, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            await page.fill('input[name="username"]', username)
            await page.fill('input[name="password"]', password)
            await page.click('#btnLogin')
            await asyncio.sleep(3)

            current_url = page.url
            if "login" not in current_url.lower():
                manager.is_logged_in = True
                await manager.screenshot("login_success")
                logger.info("Login successful, URL: %s", current_url)
                return {"status": "success", "message": "Logged in successfully"}

            logger.warning("Still on login page after attempt %d, URL: %s", attempt, current_url)

        except Exception as e:
            logger.error("Login attempt %d failed: %s", attempt, e)
            if attempt < max_retries:
                wait_time = Config.RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                await asyncio.sleep(wait_time)

    await manager.screenshot("login_failed")
    return {"status": "failed", "message": "Login failed after all retries"}


async def navigate_to_charges_form() -> dict:
    """Navigate to /charges_group/create."""
    manager = BrowserManager.get_instance()
    page = await manager.get_page()

    try:
        url = Config.CHARGES_FORM_URL
        logger.info("Navigating to charges form: %s", url)
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        title = await page.title()
        await manager.screenshot("charges_form_loaded")
        return {"status": "success", "message": "Navigated to charges form", "title": title}

    except Exception as e:
        logger.error("Navigation failed: %s", e)
        await manager.screenshot("navigation_failed")
        return {"status": "failed", "message": str(e)}


async def set_date_range(start_date: str, end_date: str) -> dict:
    """
    Set the program date range filter then wait for the dropdowns to load.
    Dates in dd/mm/yyyy format.
    """
    manager = BrowserManager.get_instance()
    page = await manager.get_page()

    try:
        await _set_input_value(page, 'input[name="start"]', start_date)
        await _set_input_value(page, 'input[name="end"]', end_date)
        await asyncio.sleep(1)
        return {"status": "success"}
    except Exception as e:
        logger.error("Date range failed: %s", e)
        return {"status": "failed", "message": str(e)}


async def select_program_and_tour(
    program_name: str = None,
    tour_code: str = None,
    date_from: str = None,
    date_to: str = None,
) -> dict:
    """
    Select tour program and tour code from Bootstrap selectpicker dropdowns.
    Optionally set the date range first so the correct options load.

    After selecting the program, waits for the tour/period dropdown to reload
    (AJAX) before selecting the tour code.
    """
    manager = BrowserManager.get_instance()
    page = await manager.get_page()

    try:
        # Set date range first so the correct programs appear
        if date_from and date_to:
            logger.info("Setting date range: %s - %s", date_from, date_to)
            await _set_input_value(page, 'input[name="start"]', date_from)
            await _set_input_value(page, 'input[name="end"]', date_to)
            await asyncio.sleep(3)

        # Select program (populates the tour/period dropdown via AJAX)
        if program_name:
            logger.info("Selecting program: %s", program_name)
            await _select_bootstrap_option(page, 'select[name="package"]', program_name)
            await asyncio.sleep(4)  # AJAX loads tour codes for selected program

        # Select tour code from the period dropdown
        if tour_code:
            logger.info("Selecting tour code: %s", tour_code)
            await _select_bootstrap_option(page, 'select[name="period"]', tour_code)
            await asyncio.sleep(1)

        await manager.screenshot("program_selected")
        return {"status": "success", "message": f"Selected program={program_name}, tour={tour_code}"}

    except Exception as e:
        logger.error("Program/tour selection failed: %s", e)
        await manager.screenshot("selection_failed")
        return {"status": "failed", "message": str(e)}


async def fill_expense_form(
    payment_date: str = None,
    receipt_date: str = None,
    receipt_number: str = "",
    description: str = "",
    charge_type: str = "flight",
    amount: float = 0,
    currency: str = "THB",
    exchange_rate: float = 1.0,
    remark: str = "",
) -> dict:
    """
    Fill the expense row fields on /charges_group/create.
    Uses the actual field names from the form.
    """
    manager = BrowserManager.get_instance()
    page = await manager.get_page()

    try:
        today = datetime.now().strftime("%d/%m/%Y")

        # Payment date
        await _set_input_value(page, 'input[name="payment_date"]', payment_date or today)

        # Receipt date (try multiple possible selectors)
        receipt_sel = await page.query_selector('input[name="receipt_date"]')
        if receipt_sel:
            await _set_input_value(page, 'input[name="receipt_date"]', receipt_date or today)

        # Receipt number
        if receipt_number:
            receipt_no_el = await page.query_selector('input[name="receipt_no"]')
            if receipt_no_el:
                await receipt_no_el.fill(str(receipt_number))

        # Description (array field for dynamic rows)
        desc_el = await page.query_selector('input[name="description[]"]')
        if desc_el:
            await desc_el.fill(description)

        # Charge type dropdown
        mapped_type = CHARGE_TYPE_MAP.get(charge_type, CHARGE_TYPE_MAP["flight"])
        await _select_bootstrap_option(page, 'select[name="rate_type[]"]', mapped_type)

        # Amount
        amount_el = await page.query_selector('input[name="price[]"]')
        if amount_el:
            await amount_el.fill(str(amount))

        # Currency
        await _select_bootstrap_option(page, '#currency', currency)

        # Exchange rate
        if exchange_rate != 1.0:
            rate_el = await page.query_selector('input[name="rate"]')
            if rate_el:
                await rate_el.fill(str(exchange_rate))

        # Remark
        if remark:
            remark_el = await page.query_selector('textarea[name="remark"]')
            if remark_el:
                await remark_el.fill(remark)

        await manager.screenshot("form_filled")
        return {"status": "success", "message": f"Form filled: {description}, {amount} {currency}"}

    except Exception as e:
        logger.error("Form filling failed: %s", e)
        await manager.screenshot("form_fill_failed")
        return {"status": "failed", "message": str(e)}


async def click_add_company_expense() -> dict:
    """
    Click the '+ เพิ่มในค่าใช้จ่ายบริษัท' button to reveal the company
    expense section (section 2) of the form.
    """
    manager = BrowserManager.get_instance()
    page = await manager.get_page()

    try:
        result = await page.evaluate("""
        (function() {
            var btn = document.querySelector('a.addChargesCompany, .addChargesCompany');
            if (!btn) return 'NOT_FOUND';
            btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
            btn.click();
            return 'CLICKED';
        })()
        """)

        if result == "NOT_FOUND":
            return {"status": "failed", "message": "addChargesCompany button not found"}

        await asyncio.sleep(2)
        await manager.screenshot("company_section_opened")
        return {"status": "success", "message": "Company expense section opened"}

    except Exception as e:
        logger.error("Failed to open company expense section: %s", e)
        return {"status": "failed", "message": str(e)}


async def fill_company_expense(
    company_name: str = "",
    payment_method: str = "โอนเข้าบัญชี",
    supplier_name: str = "",
    agent_name: str = "",
    amount: float = 0,
    fee: float = 0,
    payment_date: str = "",
    payment_type: str = "ค่าทัวร์/ค่าแลนด์",
    period: str = "",
    remark: str = "",
) -> dict:
    """
    Fill the company expense section (section 2) of the charges form.

    Args:
        company_name: Company to charge, matched against the dropdown
                      (e.g. "Go365Travel", "2U Center", "GO HOLIDAY TOUR")
        payment_method: "โอนเข้าบัญชี" (transfer) / "เช็ค" (check) / "บัตรเครดิต" (credit)
        supplier_name: Land supplier / pay-to name (translated from Chinese if needed)
        agent_name: Agent name (optional)
        amount: Payment amount
        fee: Fee (optional)
        payment_date: dd/mm/yyyy
        payment_type: Expense category from dropdown
                      (e.g. "ค่าทัวร์/ค่าแลนด์", "ค่าตั๋วเครื่องบิน")
        period: Period / tour code
        remark: Additional notes
    """
    manager = BrowserManager.get_instance()
    page = await manager.get_page()

    try:
        today = datetime.now().strftime("%d/%m/%Y")

        # Company dropdown
        if company_name:
            await _select_bootstrap_option(
                page,
                'select[name="charges[id_company_charges_agent]"]',
                company_name,
            )
            await asyncio.sleep(1)

        # Payment method dropdown
        if payment_method:
            await _select_bootstrap_option(
                page,
                'select[name="charges[payment_type]"]',
                payment_method,
            )

        # Pay to (supplier name)
        if supplier_name:
            pay_el = await page.query_selector('input[name="pay_name"]')
            if pay_el:
                await pay_el.fill(supplier_name)

        # Agent name
        if agent_name:
            agent_el = await page.query_selector('input[name="agent_name"]')
            if agent_el:
                await agent_el.fill(agent_name)

        # Amount
        if amount:
            amt_el = await page.query_selector('input[name="charges[amount]"]')
            if amt_el:
                await amt_el.fill(str(amount))

        # Fee
        if fee:
            fee_el = await page.query_selector('input[name="charges[fee]"]')
            if fee_el:
                await fee_el.fill(str(fee))

        # Payment date
        pay_date_val = payment_date or today
        await _set_input_value(page, 'input[name="charges[pay_date]"]', pay_date_val)

        # Payment type dropdown
        if payment_type:
            await _select_bootstrap_option(
                page,
                'select[name="charges[id_company_charges_type]"]',
                payment_type,
            )

        # Period
        if period:
            period_el = await page.query_selector('input[name="charges[remark_period]"]')
            if period_el:
                await period_el.fill(period)

        # Remark
        if remark:
            remark_el = await page.query_selector('textarea[name="charges[remark]"]')
            if remark_el:
                await remark_el.fill(remark)

        await manager.screenshot("company_expense_filled")
        return {
            "status": "success",
            "message": f"Company expense filled: {supplier_name}, {amount}",
        }

    except Exception as e:
        logger.error("Company expense fill failed: %s", e)
        await manager.screenshot("company_expense_failed")
        return {"status": "failed", "message": str(e)}


async def submit_form() -> dict:
    """Click the Save submit button (input[type='submit'])."""
    manager = BrowserManager.get_instance()
    page = await manager.get_page()

    try:
        submit_selectors = [
            'input[type="submit"][value="Save"]',
            'input[type="submit"]',
            'button:has-text("Save")',
            'button:has-text("บันทึก")',
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

        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(3)
        await manager.screenshot("form_submitted")
        return {"status": "success", "message": "Form submitted"}

    except Exception as e:
        logger.error("Form submission failed: %s", e)
        await manager.screenshot("submit_failed")
        return {"status": "failed", "message": str(e)}


async def extract_order_number() -> dict:
    """
    Read the expense number from #charges_no or from the page text.
    Pattern: C2026XX-XXXXXX
    """
    manager = BrowserManager.get_instance()
    page = await manager.get_page()

    try:
        # Strategy 1: Read the charges_no field
        charges_el = await page.query_selector('#charges_no')
        if charges_el:
            value = await charges_el.input_value()
            if value and value.strip() and value.strip() != "C2021XX-XXXX":
                logger.info("Extracted expense number from field: %s", value)
                return {"status": "success", "expense_number": value.strip()}

        # Strategy 2: Regex on page text
        page_text = await page.inner_text("body")
        pattern = r"C\d{6}-\d{4,6}"
        matches = re.findall(pattern, page_text)
        if matches:
            expense_no = matches[-1]
            logger.info("Extracted expense number (regex): %s", expense_no)
            return {"status": "success", "expense_number": expense_no}

        # Strategy 3: Success alert
        for sel in [".alert-success", ".alert.alert-success"]:
            el = await page.query_selector(sel)
            if el:
                text = await el.inner_text()
                return {"status": "success", "expense_number": "UNKNOWN", "message": text}

        await manager.screenshot("extract_number_failed")
        return {"status": "partial", "expense_number": "UNKNOWN", "message": "Submitted but could not read expense number"}

    except Exception as e:
        logger.error("Order number extraction failed: %s", e)
        return {"status": "failed", "message": str(e)}


async def close_browser() -> dict:
    """Gracefully close the browser session."""
    try:
        manager = BrowserManager.get_instance()
        await manager.close()
        return {"status": "success", "message": "Browser closed"}
    except Exception as e:
        logger.error("Error closing browser: %s", e)
        return {"status": "failed", "message": str(e)}


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
        logger.error("Table scraping failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _set_input_value(page, selector: str, value: str):
    """Set an input's value via JS (works for date pickers that block .fill())."""
    el = await page.query_selector(selector)
    if not el:
        logger.warning("Element not found: %s", selector)
        return
    await page.evaluate(
        """([el, val]) => {
            el.value = val;
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }""",
        [el, value],
    )


async def _select_bootstrap_option(page, selector: str, value: str):
    """
    Select a value in a Bootstrap selectpicker by clicking through the UI.

    Approach:
    1. Find the Bootstrap selectpicker toggle button next to the <select>
    2. Click it to open the dropdown overlay
    3. Type in the search box (if available) or find the matching <li>
    4. Click the matching item

    Falls back to JS-based selection if the UI approach fails.
    """
    safe_value = value.replace("\\", "\\\\").replace("'", "\\'")
    safe_selector = selector.replace("\\", "\\\\").replace("'", "\\'")

    try:
        # Strategy 1: Click through the Bootstrap selectpicker UI
        # Find the selectpicker button associated with this <select>
        toggle_btn = await page.evaluate(f"""
        (function() {{
            var sel = document.querySelector('{safe_selector}');
            if (!sel) return null;
            var parent = sel.closest('.bootstrap-select') || sel.parentElement;
            var btn = parent ? parent.querySelector('button.dropdown-toggle') : null;
            if (btn) {{
                var rect = btn.getBoundingClientRect();
                return {{ x: rect.x + rect.width/2, y: rect.y + rect.height/2, found: true }};
            }}
            return null;
        }})()
        """)

        if toggle_btn and toggle_btn.get("found"):
            # Click the toggle button to open the dropdown
            await page.mouse.click(toggle_btn["x"], toggle_btn["y"])
            await asyncio.sleep(1)

            # Find and click the matching <li> / <a> in the dropdown via JS
            clicked = await page.evaluate(f"""
            (function() {{
                var sel = document.querySelector('{safe_selector}');
                var parent = sel.closest('.bootstrap-select') || sel.parentElement;
                if (!parent) return 'NO_PARENT';

                // Try typing in the search box first (some dropdowns have it)
                var searchBox = parent.querySelector('.bs-searchbox input');
                if (searchBox) {{
                    searchBox.value = '{safe_value}';
                    searchBox.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}

                // Wait a tick for filtering, then look for matching items
                var items = parent.querySelectorAll('.dropdown-menu li:not(.hidden):not(.no-results) a');
                var target = '{safe_value}'.toLowerCase();

                for (var i = 0; i < items.length; i++) {{
                    var txt = items[i].textContent.toLowerCase().trim();
                    if (txt.includes(target) || target.includes(txt)) {{
                        items[i].click();
                        return 'CLICKED:' + items[i].textContent.substring(0, 80).trim();
                    }}
                }}
                // No exact match - click first non-placeholder item
                for (var j = 0; j < items.length; j++) {{
                    var t = items[j].textContent.trim();
                    if (t && t !== 'ทั้งหมด' && t !== 'Nothing selected') {{
                        items[j].click();
                        return 'FALLBACK:' + t.substring(0, 80);
                    }}
                }}
                return 'NO_ITEMS';
            }})()
            """)
            logger.info("Bootstrap click %s -> %s (target='%s')", selector, clicked, value)

            if clicked and (clicked.startswith("CLICKED") or clicked.startswith("FALLBACK")):
                await asyncio.sleep(0.5)
                return

        # Strategy 2: JS fallback (set selectedIndex + trigger change)
        logger.info("Falling back to JS-based selection for %s", selector)
        await _select_via_js(page, selector, value)

    except Exception as e:
        logger.warning("Dropdown selection for %s failed: %s, trying JS fallback", selector, e)
        await _select_via_js(page, selector, value)


async def _select_via_js(page, selector: str, value: str):
    """Fallback: set selectedIndex via JS and trigger change event."""
    safe_value = value.replace("\\", "\\\\").replace("'", "\\'")
    safe_selector = selector.replace("\\", "\\\\").replace("'", "\\'")

    js = f"""
    (function() {{
        var selectEl = document.querySelector('{safe_selector}');
        if (!selectEl) return 'NOT_FOUND';

        var opts = selectEl.options;
        var target = '{safe_value}'.toLowerCase();
        var foundIdx = -1;

        for (var i = 0; i < opts.length; i++) {{
            var txt = opts[i].text.toLowerCase();
            var val = opts[i].value.toLowerCase();
            if (txt.includes(target) || val.includes(target)
                || target.includes(txt) || target.includes(val)) {{
                foundIdx = i;
                break;
            }}
        }}

        if (foundIdx < 0 && opts.length > 1) foundIdx = 1;
        if (foundIdx < 0) return 'NO_MATCH';

        selectEl.selectedIndex = foundIdx;
        selectEl.dispatchEvent(new Event('change', {{ bubbles: true }}));
        try {{ jQuery(selectEl).trigger('change'); }} catch(e) {{}}

        return 'OK:' + opts[foundIdx].text.substring(0, 80);
    }})()
    """
    result = await page.evaluate(js)
    logger.info("JS select %s -> %s", selector, result)

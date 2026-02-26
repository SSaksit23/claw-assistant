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
from services import learning_service

logger = logging.getLogger(__name__)

CHARGE_TYPE_MAP = {
    "flight": "ค่าตั๋วเครื่องบิน",
    "visa": "ค่าวีซ่า",
    "allowance": "เบี้ยเลี้ยง (ค่าจ้างมัคคุเทศก์และหัวหน้าทัวร์)",
    "taxi": "ค่าแท็กซี่หัวหน้าทัวร์",
    "meal": "ค่าตั๋วเครื่องบิน",
    "accommodation": "ค่าทัวร์/ค่าแลนด์",
    "tour_guide": "เบี้ยเลี้ยง (ค่าจ้างมัคคุเทศก์และหัวหน้าทัวร์)",
    "land_tour": "ค่าทัวร์/ค่าแลนด์",
    "single_supplement": "ค่าทัวร์/ค่าแลนด์",
    "service_fee": "ค่าทัวร์/ค่าแลนด์",
    "guide_tip": "เบี้ยเลี้ยง (ค่าจ้างมัคคุเทศก์และหัวหน้าทัวร์)",
    "transport": "ค่าแท็กซี่หัวหน้าทัวร์",
    "insurance": "ค่าทัวร์/ค่าแลนด์",
    "entrance_fee": "ค่าทัวร์/ค่าแลนด์",
    "other": "ค่าทัวร์/ค่าแลนด์",
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


async def search_program_code(group_code: str, session_id: str = "default") -> dict:
    """
    Look up the program code for a given group/tour code by searching on
    /travelpackage.

    The search tries the full group code first, then progressively shorter
    prefixes (first 10, 7, 5 characters) until a match is found.

    Returns {"status": "success", "program_code": "...", "program_name": "..."}
            or {"status": "not_found", ...}
    """
    manager = BrowserManager.get_instance(session_id)
    page = await manager.get_page()

    # Build candidate search terms: full code, then shorter prefixes
    candidates = [group_code]
    for length in (10, 7, 5):
        prefix = group_code[:length]
        if prefix not in candidates and len(prefix) >= 5:
            candidates.append(prefix)

    try:
        url = Config.TRAVEL_PACKAGE_URL
        logger.info("Navigating to travelpackage: %s", url)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception as nav_err:
            logger.warning("travelpackage page.goto failed: %s — retrying with new page", nav_err)
            try:
                await manager.reset()
                page = await manager.get_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            except Exception as retry_err:
                logger.error("travelpackage retry also failed: %s", retry_err)
                return {"status": "failed", "message": f"Cannot load travelpackage page: {retry_err}"}
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
                logger.info(
                    "Found program code %s for group %s (searched '%s')",
                    match["program_code"], group_code, search_term,
                )
                return {"status": "success", **match}

        return {
            "status": "not_found",
            "message": f"No program code found for '{group_code}' (tried: {candidates})",
        }

    except Exception as e:
        logger.error("Program search failed: %s", e, exc_info=True)
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


async def login(username: str = None, password: str = None, max_retries: int = 3, session_id: str = "default") -> dict:
    """
    Log in to qualityb2bpackage.com.
    The login button is #btnLogin (type="button", JS-driven).
    Forces re-login when a different user's credentials are provided.
    """
    manager = BrowserManager.get_instance(session_id)
    username = username or Config.WEBSITE_USERNAME
    password = password or Config.WEBSITE_PASSWORD

    if manager.is_logged_in:
        if manager.logged_in_username and manager.logged_in_username != username:
            logger.info("Different user (%s -> %s), forcing re-login for session=%s",
                        manager.logged_in_username, username, session_id)
            page = await manager.get_page()
            try:
                await page.context.clear_cookies()
            except Exception:
                pass
            manager.is_logged_in = False
            manager.logged_in_username = None
        else:
            return {"status": "success", "message": "Already logged in"}

    page = await manager.get_page()

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Login attempt %d/%d for user=%s", attempt, max_retries, username)
            await page.goto(Config.WEBSITE_URL, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)

            await page.fill('input[name="username"]', username)
            await page.fill('input[name="password"]', password)
            await page.click('#btnLogin')
            await asyncio.sleep(3)

            current_url = page.url
            if "login" not in current_url.lower():
                manager.is_logged_in = True
                manager.logged_in_username = username
                await manager.screenshot("login_success")
                logger.info("Login successful for user=%s, URL: %s", username, current_url)
                return {"status": "success", "message": "Logged in successfully"}

            logger.warning("Still on login page after attempt %d, URL: %s", attempt, current_url)

        except Exception as e:
            logger.error("Login attempt %d failed: %s", attempt, e)
            if attempt < max_retries:
                wait_time = Config.RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                await asyncio.sleep(wait_time)

    await manager.screenshot("login_failed")
    learning_service.log_error(
        agent="Accounting Agent",
        error_type="login_failed",
        summary="Login to qualityb2bpackage.com failed after all retries",
        error_message="All login attempts exhausted",
        context="Check credentials, site availability, and network connectivity",
        related_files=["tools/browser_tools.py", "config.py"],
    )
    return {"status": "failed", "message": "Login failed after all retries"}


async def navigate_to_charges_form(session_id: str = "default") -> dict:
    """Navigate to /charges_group/create."""
    manager = BrowserManager.get_instance(session_id)
    page = await manager.get_page()

    try:
        url = Config.CHARGES_FORM_URL
        logger.info("Navigating to charges form: %s (current: %s)", url, page.url)

        if not getattr(page, '_dialog_handler_set', False):
            async def _auto_dismiss(dialog):
                try:
                    await dialog.accept()
                except Exception:
                    pass
            page.on("dialog", _auto_dismiss)
            page._dialog_handler_set = True

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as goto_err:
            logger.warning("page.goto failed: %s — checking if page loaded anyway", goto_err)
            current_url = page.url
            if "charges_group" in current_url:
                logger.info("Page DID navigate to %s despite error", current_url)
            else:
                logger.warning("Page still at %s, trying direct JS navigation", current_url)
                try:
                    await page.evaluate(f"window.location.href = '{url}'")
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass

        await asyncio.sleep(2)

        current_url = page.url
        if "member/login" in current_url or "login" in current_url.split("/")[-1].lower():
            logger.warning("Redirected to login page (%s) — session expired, need re-login", current_url)
            manager.is_logged_in = False
            return {"status": "failed", "message": "Session expired — redirected to login page"}

        title = await page.title()
        logger.info("Charges form page loaded: title='%s' url='%s'", title, page.url)
        return {"status": "success", "message": "Navigated to charges form", "title": title}

    except Exception as e:
        logger.error("Navigation failed: %s", e, exc_info=True)
        try:
            await manager.screenshot("navigation_failed")
        except Exception:
            pass
        return {"status": "failed", "message": str(e)}


async def set_date_range(start_date: str, end_date: str, session_id: str = "default") -> dict:
    """
    Set the program date range filter then wait for the dropdowns to load.
    Dates in dd/mm/yyyy format.
    """
    manager = BrowserManager.get_instance(session_id)
    page = await manager.get_page()

    try:
        await _set_input_value(page, 'input[name="start"]', start_date)
        await _set_input_value(page, 'input[name="end"]', end_date)
        await asyncio.sleep(1)
        return {"status": "success"}
    except Exception as e:
        logger.error("Date range failed: %s", e)
        return {"status": "failed", "message": str(e)}


async def _dismiss_overlays(page):
    """Click body to dismiss any datepicker popups or dropdown overlays."""
    try:
        await page.evaluate("""
        (function() {
            // Close any open Bootstrap datepickers
            var dps = document.querySelectorAll('.datepicker');
            dps.forEach(function(dp) { dp.style.display = 'none'; });
            // Close any open Bootstrap select dropdowns
            var opens = document.querySelectorAll('.bootstrap-select.open');
            opens.forEach(function(el) { el.classList.remove('open'); });
            // Click body to dismiss misc popups
            document.body.click();
        })()
        """)
        await asyncio.sleep(0.3)
    except Exception:
        pass


async def select_program_and_tour(
    program_name: str = None,
    tour_code: str = None,
    date_from: str = None,
    date_to: str = None,
    session_id: str = "default",
) -> dict:
    """
    Select tour program and tour code from Bootstrap selectpicker dropdowns.
    Optionally set the date range first so the correct options load.

    After selecting the program, waits for the tour/period dropdown to reload
    (AJAX) before selecting the tour code.
    """
    manager = BrowserManager.get_instance(session_id)
    page = await manager.get_page()

    try:
        # Set date range first so the correct programs appear
        if date_from and date_to:
            logger.info("select_program_and_tour: [1/6] setting start date %s", date_from)
            await _set_input_value(page, 'input[name="start"]', date_from)
            logger.info("select_program_and_tour: [2/6] setting end date %s", date_to)
            await _set_input_value(page, 'input[name="end"]', date_to)
            await asyncio.sleep(1)
            logger.info("select_program_and_tour: [3/6] dismissing overlays")
            await _dismiss_overlays(page)
            logger.info("select_program_and_tour: date range set OK")
            await asyncio.sleep(2)

        # Select program via JS directly (faster and more reliable than Bootstrap UI clicks)
        if program_name:
            logger.info("select_program_and_tour: [4/6] selecting program %s", program_name)
            await _js_select_option(page, 'select[name="package"]', program_name)
            await asyncio.sleep(4)
            logger.info("select_program_and_tour: program selected, AJAX waited")

        # Select tour code via JS directly
        if tour_code:
            logger.info("select_program_and_tour: [5/6] selecting tour code %s", tour_code)
            await _js_select_option(page, 'select[name="period"]', tour_code)
            await asyncio.sleep(1)

        logger.info("select_program_and_tour: [6/6] done")
        return {"status": "success", "message": f"Selected program={program_name}, tour={tour_code}"}

    except Exception as e:
        logger.error("Program/tour selection failed: %s", e, exc_info=True)
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
    session_id: str = "default",
) -> dict:
    """
    Fill the expense row fields on /charges_group/create.
    Uses the actual field names from the form.
    """
    manager = BrowserManager.get_instance(session_id)
    page = await manager.get_page()

    try:
        today = datetime.now().strftime("%d/%m/%Y")

        # Wait for page to settle after AJAX tour selection
        logger.info("fill_expense_form: waiting for page to settle...")
        await asyncio.sleep(2)
        await _dismiss_overlays(page)

        # Payment date
        logger.info("fill_expense_form: setting payment_date")
        await _set_input_value(page, 'input[name="payment_date"]', payment_date or today)

        # Receipt date (try multiple possible selectors)
        receipt_sel = await page.query_selector('input[name="receipt_date"]')
        if receipt_sel:
            logger.info("fill_expense_form: setting receipt_date")
            await _set_input_value(page, 'input[name="receipt_date"]', receipt_date or today)

        # Receipt number
        if receipt_number:
            receipt_no_el = await page.query_selector('input[name="receipt_no"]')
            if receipt_no_el:
                await receipt_no_el.fill(str(receipt_number))

        # Description (array field for dynamic rows)
        logger.info("fill_expense_form: setting description")
        desc_el = await page.query_selector('input[name="description[]"]')
        if desc_el:
            await desc_el.fill(description)
        else:
            logger.warning("fill_expense_form: description[] not found, trying JS fallback")
            await page.evaluate("""
                var el = document.querySelector('input[name="description[]"]');
                if (el) { el.value = arguments[0]; el.dispatchEvent(new Event('change', {bubbles:true})); }
            """)

        # Charge type dropdown — use JS fallback with timeout
        logger.info("fill_expense_form: setting charge_type")
        mapped_type = CHARGE_TYPE_MAP.get(charge_type, CHARGE_TYPE_MAP["flight"])
        await _js_select_option(page, 'select[name="rate_type[]"]', mapped_type)

        # Amount
        logger.info("fill_expense_form: setting amount=%s", amount)
        amount_el = await page.query_selector('input[name="price[]"]')
        if amount_el:
            await amount_el.fill(str(amount))
        else:
            logger.warning("fill_expense_form: price[] not found")

        # Currency
        logger.info("fill_expense_form: setting currency=%s", currency)
        await _js_select_option(page, '#currency', currency)

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

        logger.info("fill_expense_form: all fields set, taking screenshot")
        try:
            await manager.screenshot("form_filled")
        except Exception:
            pass
        return {"status": "success", "message": f"Form filled: {description}, {amount} {currency}"}

    except Exception as e:
        logger.error("Form filling failed: %s", e)
        try:
            await manager.screenshot("form_fill_failed")
        except Exception:
            pass
        return {"status": "failed", "message": str(e)}


async def _add_expense_row(page) -> bool:
    """Click the 'add row' button to create a new expense line item row."""
    result = await page.evaluate("""
    (function() {
        // Look for common "add row" buttons
        var selectors = [
            'a.addDetail', '.addDetail', 'a.add-row', '.add-row',
            'button.addDetail', 'a[onclick*="addDetail"]',
            'a.btn-add-row', '.btn-add-detail',
            'a:has(i.fa-plus)', 'button:has(i.fa-plus)',
        ];
        for (var s of selectors) {
            var btn = document.querySelector(s);
            if (btn) {
                btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                btn.click();
                return 'CLICKED:' + s;
            }
        }
        // Fallback: look for any link/button with "เพิ่ม" (add) in text that's near expense rows
        var links = document.querySelectorAll('a, button');
        for (var l of links) {
            var txt = l.textContent.trim();
            if ((txt.includes('เพิ่ม') || txt.includes('+')) &&
                !txt.includes('บริษัท') && l.offsetParent !== null) {
                l.scrollIntoView({ behavior: 'smooth', block: 'center' });
                l.click();
                return 'CLICKED_TEXT:' + txt.substring(0, 40);
            }
        }
        return 'NOT_FOUND';
    })()
    """)
    logger.info("_add_expense_row: %s", result)
    await asyncio.sleep(1)
    return result != "NOT_FOUND"


async def fill_expense_rows(
    rows: list[dict],
    payment_date: str = None,
    session_id: str = "default",
) -> dict:
    """
    Fill the expense section on /charges_group/create.

    Combines all line items into a single form row with the TOTAL amount
    and a clean, structured description.

    Each row dict should contain:
        - amount, currency, exchange_rate, charge_type
        - expense_label: English name (e.g., "Airline Ticket")
        - formatted_description: pre-built multi-line description block
        - remark: detailed remark text (on first row only)
    """
    manager = BrowserManager.get_instance(session_id)
    page = await manager.get_page()

    if not rows:
        return {"status": "failed", "message": "No rows to fill"}

    today = datetime.now().strftime("%d/%m/%Y")
    currency = rows[0].get("currency", "THB")
    exchange_rate = rows[0].get("exchange_rate", 1.0)

    total_amount = sum(r.get("amount", 0) for r in rows)

    # Build a concise description for the form input field.
    # Single item: "Airline Ticket 21 Pax x 6,200 = 130,200 CNY"
    # Multi items:  "Tour Fare + Single Room Supplement + Service Fee = 98,180 CNY"
    if len(rows) == 1:
        r = rows[0]
        label = r.get("expense_label") or r.get("charge_type", "Other")
        amt = r.get("amount", 0)
        pax = r.get("pax")
        up = r.get("unit_price")
        if pax and up:
            combined_desc = f"{label} {pax} Pax x {up:,.0f} = {amt:,.0f} {currency}"
        else:
            combined_desc = f"{label} {amt:,.0f} {currency}"
    else:
        labels = [r.get("expense_label") or r.get("charge_type", "Other") for r in rows]
        combined_desc = f"{' + '.join(labels)} = {total_amount:,.0f} {currency}"

    primary_row = max(rows, key=lambda r: r.get("amount", 0))
    primary_charge_type = primary_row.get("charge_type", "other")

    logger.info("fill_expense_rows: %d items, total=%s %s, desc=%s",
                len(rows), total_amount, currency, combined_desc[:100])

    try:
        await asyncio.sleep(1)
        await _dismiss_overlays(page)

        # Payment date
        logger.info("fill_expense_rows: setting payment_date")
        await _set_input_value(page, 'input[name="payment_date"]', payment_date or today)

        # Receipt date
        receipt_sel = await page.query_selector('input[name="receipt_date"]')
        if receipt_sel:
            await _set_input_value(page, 'input[name="receipt_date"]', payment_date or today)

        # Description — concise one-liner
        logger.info("fill_expense_rows: setting description")
        desc_el = await page.query_selector('input[name="description[]"]')
        if desc_el:
            await desc_el.fill(combined_desc)
        else:
            logger.warning("fill_expense_rows: description[] not found")

        # Charge type dropdown
        logger.info("fill_expense_rows: setting charge_type=%s", primary_charge_type)
        mapped_type = CHARGE_TYPE_MAP.get(primary_charge_type, CHARGE_TYPE_MAP.get("other", "ค่าทัวร์/ค่าแลนด์"))
        await _js_select_option(page, 'select[name="rate_type[]"]', mapped_type)

        # Amount — TOTAL of all line items
        logger.info("fill_expense_rows: setting TOTAL amount=%s", total_amount)
        price_el = await page.query_selector('input[name="price[]"]')
        if price_el:
            await price_el.fill(str(total_amount))
        else:
            logger.warning("fill_expense_rows: price[] not found")

        # Currency
        logger.info("fill_expense_rows: setting currency=%s", currency)
        await _js_select_option(page, '#currency', currency)

        # Exchange rate
        if exchange_rate != 1.0:
            rate_el = await page.query_selector('input[name="rate"]')
            if rate_el:
                await rate_el.fill(str(exchange_rate))

        # Remark — full structured breakdown
        remark_text = rows[0].get("remark", "")
        if remark_text:
            remark_el = await page.query_selector('textarea[name="remark"]')
            if remark_el:
                await remark_el.fill(remark_text)

        logger.info("fill_expense_rows: done, total=%s %s (%d items combined)",
                    total_amount, currency, len(rows))
        return {
            "status": "success",
            "message": f"Filled expense: {total_amount:,.0f} {currency} ({len(rows)} items combined)",
            "rows_filled": [{"description": combined_desc, "amount": total_amount, "charge_type": primary_charge_type}],
            "total_amount": total_amount,
        }

    except Exception as e:
        logger.error("fill_expense_rows failed: %s", e, exc_info=True)
        learning_service.log_error(
            agent="Accounting Agent",
            error_type="form_fill_failed",
            summary=f"fill_expense_rows failed: {len(rows)} items, total={total_amount}",
            error_message=str(e),
            context=f"Items: {len(rows)}, Total: {total_amount} {currency}",
            suggested_fix="Check form selectors and bootstrap dropdown state",
            related_files=["tools/browser_tools.py"],
        )
        try:
            await manager.screenshot("expense_rows_failed")
        except Exception:
            pass
        return {"status": "failed", "message": str(e), "rows_filled": []}


async def click_add_company_expense(session_id: str = "default") -> dict:
    """
    Click the '+ เพิ่มในค่าใช้จ่ายบริษัท' button to reveal the company
    expense section (section 2) of the form.
    """
    manager = BrowserManager.get_instance(session_id)
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
    session_id: str = "default",
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
    manager = BrowserManager.get_instance(session_id)
    page = await manager.get_page()

    try:
        today = datetime.now().strftime("%d/%m/%Y")

        await _dismiss_overlays(page)

        # Company dropdown (auto-populates the supplier/pay_name field)
        company_selected = False
        if company_name:
            logger.info("fill_company_expense: setting company=%s", company_name)
            await _js_select_option(page, 'select[name="charges[id_company_charges_agent]"]', company_name)
            company_selected = True
            await asyncio.sleep(2)

        # Payment method dropdown
        if payment_method:
            logger.info("fill_company_expense: setting payment_method=%s", payment_method)
            await _js_select_option(page, 'select[name="charges[payment_type]"]', payment_method)

        # Pay to / supplier name (สั่งจ่ายชื่อ/บริษัทที่สั่งจ่าย)
        # MUST be filled AFTER the company dropdown, because the dropdown's
        # onchange JS auto-fills pay_name with the company name.
        # We overwrite it with the actual supplier from the invoice.
        if supplier_name:
            logger.info("fill_company_expense: setting supplier=%s", supplier_name[:50])
            await asyncio.sleep(1)
            pay_selectors = [
                'input[name="pay_name"]',
                'input[name="charges[pay_name]"]',
                'input[name="charges[company_name]"]',
            ]
            pay_el = None
            for sel in pay_selectors:
                pay_el = await page.query_selector(sel)
                if pay_el:
                    logger.info("fill_company_expense: found supplier input at %s", sel)
                    break

            if pay_el:
                await pay_el.click()
                await pay_el.fill("")
                await asyncio.sleep(0.3)
                await pay_el.type(supplier_name, delay=30)
                verify = await pay_el.input_value()
                logger.info("fill_company_expense: supplier verify='%s'", verify[:60] if verify else "")
                if not verify or verify.strip() != supplier_name.strip():
                    logger.warning("fill_company_expense: supplier verify mismatch, retrying with JS")
                    await page.evaluate(
                        """(args) => {
                            const [selector, val] = args;
                            const el = document.querySelector(selector);
                            if (el) { el.value = val; el.dispatchEvent(new Event('input', {bubbles:true})); }
                        }""",
                        [pay_selectors[0], supplier_name],
                    )
            else:
                logger.warning("fill_company_expense: pay_name input NOT FOUND on page")
                await manager.screenshot("pay_name_not_found")
        else:
            logger.info("fill_company_expense: no supplier name provided, leaving pay_name as-is")

        # Agent name
        if agent_name:
            agent_el = await page.query_selector('input[name="agent_name"]')
            if agent_el:
                await agent_el.fill(agent_name)

        # Amount
        if amount:
            logger.info("fill_company_expense: setting amount=%s", amount)
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
        logger.info("fill_company_expense: setting pay_date=%s", pay_date_val)
        await _set_input_value(page, 'input[name="charges[pay_date]"]', pay_date_val)
        await _dismiss_overlays(page)

        # Payment type dropdown
        if payment_type:
            logger.info("fill_company_expense: setting payment_type=%s", payment_type)
            await _js_select_option(page, 'select[name="charges[id_company_charges_type]"]', payment_type)

        # Period
        if period:
            logger.info("fill_company_expense: setting period=%s", period)
            period_el = await page.query_selector('input[name="charges[remark_period]"]')
            if period_el:
                await period_el.fill(period)

        # Remark
        if remark:
            remark_el = await page.query_selector('textarea[name="charges[remark]"]')
            if remark_el:
                await remark_el.fill(remark)

        logger.info("fill_company_expense: done")
        return {
            "status": "success",
            "message": f"Company expense filled: {supplier_name}, {amount}",
        }

    except Exception as e:
        logger.error("Company expense fill failed: %s", e, exc_info=True)
        return {"status": "failed", "message": str(e)}


async def submit_form(session_id: str = "default") -> dict:
    """Click the Save submit button (input[type='submit'])."""
    manager = BrowserManager.get_instance(session_id)
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

        logger.info("submit_form: clicked submit, waiting for page load...")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            logger.warning("submit_form: domcontentloaded timed out, continuing")
        await asyncio.sleep(3)
        logger.info("submit_form: done")
        return {"status": "success", "message": "Form submitted"}

    except Exception as e:
        logger.error("Form submission failed: %s", e, exc_info=True)
        return {"status": "failed", "message": str(e)}


async def extract_order_number(session_id: str = "default") -> dict:
    """
    Read the expense number from #charges_no or from the page text.
    Pattern: C2026XX-XXXXXX
    """
    manager = BrowserManager.get_instance(session_id)
    page = await manager.get_page()

    try:
        # Wait for page to settle after submit redirect
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            logger.warning("extract_order_number: page load wait timed out, continuing")

        # Strategy 1: Read the charges_no field
        try:
            charges_el = await asyncio.wait_for(
                page.query_selector('#charges_no'), timeout=5)
            if charges_el:
                value = await asyncio.wait_for(
                    charges_el.input_value(), timeout=5)
                if value and value.strip() and value.strip() != "C2021XX-XXXX":
                    logger.info("Extracted expense number from field: %s", value)
                    return {"status": "success", "expense_number": value.strip()}
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning("extract_order_number: strategy 1 failed: %s", e)

        # Strategy 2: Regex on page text (with timeout to prevent hang)
        try:
            page_text = await asyncio.wait_for(
                page.inner_text("body"), timeout=10)
            pattern = r"C\d{6}-\d{4,6}"
            matches = re.findall(pattern, page_text)
            if matches:
                expense_no = matches[-1]
                logger.info("Extracted expense number (regex): %s", expense_no)
                return {"status": "success", "expense_number": expense_no}
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning("extract_order_number: strategy 2 failed: %s", e)

        # Strategy 3: URL-based extraction (charges/manage/{id})
        current_url = page.url
        url_match = re.search(r'/charges(?:_group)?/(?:manage|edit)/(\d+)', current_url)
        if url_match:
            expense_id = url_match.group(1)
            logger.info("Extracted expense ID from URL: %s", expense_id)
            return {"status": "success", "expense_number": expense_id}

        # Strategy 4: Success alert
        for sel in [".alert-success", ".alert.alert-success"]:
            try:
                el = await asyncio.wait_for(
                    page.query_selector(sel), timeout=3)
                if el:
                    text = await asyncio.wait_for(el.inner_text(), timeout=3)
                    return {"status": "success", "expense_number": "UNKNOWN", "message": text}
            except (asyncio.TimeoutError, Exception):
                continue

        try:
            await manager.screenshot("extract_number_failed")
        except Exception:
            pass
        return {"status": "partial", "expense_number": "UNKNOWN", "message": "Submitted but could not read expense number"}

    except Exception as e:
        logger.error("Order number extraction failed: %s", e)
        return {"status": "failed", "message": str(e)}


async def navigate_to_manage_page(session_id: str = "default") -> dict:
    """
    After form submission, find and click the 'ไปยังหน้าค่าใช้จ่าย' link
    to navigate to /charges/manage/{id}.
    Returns the manage page URL and expense ID.
    """
    manager = BrowserManager.get_instance(session_id)
    page = await manager.get_page()

    try:
        link_selectors = [
            'a[href*="/charges/manage/"]:has-text("ไปยังหน้าค่าใช้จ่าย")',
            'a[href*="/charges/manage/"]',
            'a.btn-primary[href*="/charges/manage/"]',
        ]

        manage_href = None
        for sel in link_selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    manage_href = await el.get_attribute("href")
                    if manage_href:
                        break
            except Exception:
                continue

        if not manage_href:
            page_html = await page.content()
            match = re.search(r'href="(/charges/manage/\d+)"', page_html)
            if match:
                manage_href = match.group(1)

        if not manage_href:
            await manager.screenshot("manage_link_not_found")
            return {"status": "failed", "message": "Could not find manage page link"}

        expense_id = re.search(r'/charges/manage/(\d+)', manage_href)
        expense_id = expense_id.group(1) if expense_id else "unknown"

        full_url = manage_href if manage_href.startswith("http") else f"{Config.WEBSITE_URL.rstrip('/')}{manage_href}"
        logger.info("Navigating to manage page: %s", full_url)

        try:
            await page.goto(full_url, wait_until="commit", timeout=15000)
            logger.info("navigate_to_manage_page: page.goto completed (commit)")
        except Exception as nav_err:
            logger.warning("navigate_to_manage_page: goto timed out or failed: %s, retrying with networkidle skip", nav_err)
            try:
                await page.goto(full_url, wait_until="domcontentloaded", timeout=10000)
            except Exception:
                logger.warning("navigate_to_manage_page: second goto also failed, continuing anyway")

        await asyncio.sleep(2)
        logger.info("navigate_to_manage_page: sleep done, taking screenshot")
        await manager.screenshot("manage_page_loaded")
        logger.info("On manage page for expense_id=%s", expense_id)
        return {"status": "success", "expense_id": expense_id, "url": full_url}

    except Exception as e:
        logger.error("navigate_to_manage_page failed: %s", e, exc_info=True)
        return {"status": "failed", "message": str(e)}


async def fill_manage_page_details(
    company_name: str = "",
    supplier_name: str = "",
    session_id: str = "default",
) -> dict:
    """
    On the /charges/manage/{id} page, select the company from the dropdown
    and fill the supplier name (สั่งจ่ายชื่อ/บริษัทที่สั่งจ่าย).

    Args:
        company_name: Company to select (e.g. "Go365Travel", "GO 365 TRAVEL")
        supplier_name: Pay-to / supplier name
    """
    manager = BrowserManager.get_instance(session_id)
    page = await manager.get_page()

    try:
        await _dismiss_overlays(page)

        if company_name:
            logger.info("fill_manage_page: selecting company=%s", company_name)
            company_selectors = [
                'select[name="id_company_charges_agent"]',
                'select[name="charges[id_company_charges_agent]"]',
                'select.selectpicker[data-live-search="true"]',
            ]
            selected = False
            for sel in company_selectors:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        result = await _js_select_option(page, sel, company_name)
                        logger.info("Company select result (%s): %s", sel, result)
                        selected = True
                        await asyncio.sleep(1)
                        break
                except Exception as e:
                    logger.debug("Company selector %s failed: %s", sel, e)
                    continue

            if not selected:
                logger.warning("fill_manage_page: could not find company dropdown")

        if supplier_name:
            logger.info("fill_manage_page: filling supplier=%s", supplier_name[:60])
            await asyncio.sleep(0.5)
            supplier_selectors = [
                'input[name="pay_name"]',
                'input[name="charges[pay_name]"]',
                'input[name="charges[company_name]"]',
            ]
            filled = False
            for sel in supplier_selectors:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.fill("")
                        await el.fill(supplier_name)
                        logger.info("Supplier filled via %s", sel)
                        filled = True
                        break
                except Exception as e:
                    logger.debug("Supplier selector %s failed: %s", sel, e)
                    continue

            if not filled:
                logger.warning("fill_manage_page: pay_name input NOT FOUND, trying label search")
                try:
                    label = await page.query_selector('label:has-text("สั่งจ่าย")')
                    if label:
                        label_for = await label.get_attribute("for")
                        if label_for:
                            inp = await page.query_selector(f"#{label_for}")
                            if inp:
                                await inp.fill("")
                                await inp.fill(supplier_name)
                                filled = True
                                logger.info("Supplier filled via label for=%s", label_for)
                except Exception as e:
                    logger.debug("Label-based supplier fill failed: %s", e)

            if not filled:
                logger.warning("fill_manage_page: supplier name NOT filled")

        save_selectors = [
            'input[type="submit"][value="Save"]',
            'input[type="submit"]',
            'button:has-text("Save")',
            'button:has-text("บันทึก")',
        ]
        for sel in save_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    logger.info("fill_manage_page: clicked save via %s", sel)
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=10000)
                    except Exception:
                        pass
                    await asyncio.sleep(2)
                    break
            except Exception:
                continue

        await manager.screenshot("manage_page_filled")
        return {
            "status": "success",
            "message": f"Manage page updated: company={company_name}, supplier={supplier_name[:40]}",
        }

    except Exception as e:
        logger.error("fill_manage_page_details failed: %s", e, exc_info=True)
        return {"status": "failed", "message": str(e)}


async def close_browser(session_id: str = "default") -> dict:
    """Gracefully close the browser session."""
    try:
        await BrowserManager.destroy_instance(session_id)
        return {"status": "success", "message": "Browser closed"}
    except Exception as e:
        logger.error("Error closing browser: %s", e)
        return {"status": "failed", "message": str(e)}


async def scrape_table_data(page=None, session_id: str = "default") -> list:
    """Extract data from HTML tables on the current page."""
    if page is None:
        manager = BrowserManager.get_instance(session_id)
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

async def _js_select_option(page, selector: str, value: str):
    """Select an <option> by value using pure JS with fuzzy matching.
    Handles case-insensitive comparison and normalizes spaces/digits
    (e.g. 'Go365Travel' matches 'GO 365 TRAVEL CO., LTD.')."""
    safe_val = value.replace("\\", "\\\\").replace("'", "\\'")
    safe_sel = selector.replace("\\", "\\\\").replace("'", "\\'")
    result = await page.evaluate(f"""
    (function() {{
        var sel = document.querySelector('{safe_sel}');
        if (!sel) return 'not_found';
        var needle = '{safe_val}'.toLowerCase().replace(/[\\s.,']+/g, '');
        var bestIdx = -1;
        var bestScore = 0;
        for (var i = 0; i < sel.options.length; i++) {{
            var optVal = (sel.options[i].value || '').toLowerCase().replace(/[\\s.,']+/g, '');
            var optTxt = (sel.options[i].text || '').toLowerCase().replace(/[\\s.,']+/g, '');
            if (optVal === needle || optTxt === needle) {{
                bestIdx = i; break;
            }}
            if (optTxt.indexOf(needle) >= 0 || optVal.indexOf(needle) >= 0) {{
                var score = needle.length;
                if (score > bestScore) {{ bestScore = score; bestIdx = i; }}
            }}
            if (needle.indexOf(optTxt) >= 0 && optTxt.length > 3) {{
                var score2 = optTxt.length;
                if (score2 > bestScore) {{ bestScore = score2; bestIdx = i; }}
            }}
        }}
        if (bestIdx >= 0) {{
            sel.selectedIndex = bestIdx;
            sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
            if (typeof jQuery !== 'undefined' && jQuery(sel).selectpicker) {{
                jQuery(sel).selectpicker('refresh');
            }}
            return 'selected:' + sel.options[bestIdx].text;
        }}
        return 'no_match';
    }})()
    """)
    logger.info("JS select %s -> %s (value=%s)", selector, result, value)
    return result


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

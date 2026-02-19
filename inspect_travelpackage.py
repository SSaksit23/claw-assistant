"""
Script to inspect the travel package search page
"""
import asyncio
import json
import sys
from playwright.async_api import async_playwright

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

async def inspect_travelpackage_page():
    """Login and inspect the travel package search functionality."""
    
    async with async_playwright() as p:
        # Launch browser in headed mode
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        
        print("=" * 80)
        print("STEP 1: LOGIN")
        print("=" * 80)
        
        # Navigate to login page
        print("\nNavigating to login page...")
        await page.goto("https://www.qualityb2bpackage.com/member/login", 
                       wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)
        
        print(f"Current URL: {page.url}")
        
        # Fill credentials
        print("\nFilling credentials...")
        await page.fill('input[name="username"]', 'noi')
        await page.fill('input[name="password"]', 'PrayuthChanocha112')
        
        # Click login
        print("Clicking login button...")
        await page.click('#btnLogin')
        await asyncio.sleep(5)
        
        # Verify login
        if "login" not in page.url.lower():
            print("[SUCCESS] Logged in successfully!")
            print(f"Current URL: {page.url}")
        else:
            print("[FAILED] Login failed")
            await page.screenshot(path="logs/login_failed.png", full_page=True)
            await browser.close()
            return
        
        print("\n" + "=" * 80)
        print("STEP 2: NAVIGATE TO TRAVEL PACKAGE PAGE")
        print("=" * 80)
        
        # Navigate to travel package page
        print("\nNavigating to travel package page...")
        await page.goto("https://www.qualityb2bpackage.com/travelpackage",
                       wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)
        
        print(f"Current URL: {page.url}")
        try:
            title = await page.title()
            print(f"Page title: {title}")
        except Exception as e:
            print(f"Page title: [encoding error]")
        
        # Take screenshot
        await page.screenshot(path="logs/travelpackage_page.png", full_page=True)
        print("\nScreenshot saved: logs/travelpackage_page.png")
        
        print("\n" + "=" * 80)
        print("STEP 3: INSPECT SEARCH FUNCTIONALITY")
        print("=" * 80)
        
        # Get page HTML
        page_html = await page.content()
        
        # Find all input fields
        print("\n--- ALL INPUT FIELDS ---")
        inputs = await page.query_selector_all("input")
        input_info = []
        for i, inp in enumerate(inputs):
            inp_type = await inp.get_attribute("type") or "text"
            inp_name = await inp.get_attribute("name") or ""
            inp_id = await inp.get_attribute("id") or ""
            inp_class = await inp.get_attribute("class") or ""
            inp_placeholder = await inp.get_attribute("placeholder") or ""
            
            # Check if visible
            try:
                is_visible = await inp.is_visible()
            except:
                is_visible = False
            
            if is_visible and inp_type not in ['hidden', 'checkbox', 'radio']:
                info = {
                    "index": i,
                    "type": inp_type,
                    "name": inp_name,
                    "id": inp_id,
                    "class": inp_class,
                    "placeholder": inp_placeholder,
                    "visible": is_visible,
                }
                input_info.append(info)
                print(f"\nInput {i}:")
                print(f"  Type: {inp_type}")
                print(f"  Name: {inp_name}")
                print(f"  ID: {inp_id}")
                print(f"  Class: {inp_class}")
                print(f"  Placeholder: {inp_placeholder}")
                print(f"  Visible: {is_visible}")
        
        # Find search-related inputs
        print("\n--- SEARCH-RELATED INPUTS ---")
        search_selectors = [
            'input[type="search"]',
            'input[name*="search"]',
            'input[placeholder*="search"]',
            'input[placeholder*="Search"]',
            'input[id*="search"]',
            'input[class*="search"]',
            '.dataTables_filter input',
            '#search',
            'input[name="group_code"]',
            'input[name="code"]',
        ]
        
        for sel in search_selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    is_visible = await el.is_visible()
                    if is_visible:
                        inp_type = await el.get_attribute("type") or "text"
                        inp_name = await el.get_attribute("name") or ""
                        inp_id = await el.get_attribute("id") or ""
                        inp_class = await el.get_attribute("class") or ""
                        inp_placeholder = await el.get_attribute("placeholder") or ""
                        
                        print(f"\n[FOUND] Selector: {sel}")
                        print(f"  Type: {inp_type}")
                        print(f"  Name: {inp_name}")
                        print(f"  ID: {inp_id}")
                        print(f"  Class: {inp_class}")
                        print(f"  Placeholder: {inp_placeholder}")
            except Exception as e:
                pass
        
        # Find all buttons
        print("\n--- ALL BUTTONS ---")
        buttons = await page.query_selector_all("button, input[type='submit'], input[type='button']")
        button_info = []
        for i, btn in enumerate(buttons):
            try:
                is_visible = await btn.is_visible()
                if not is_visible:
                    continue
                    
                tag_name = await btn.evaluate("el => el.tagName.toLowerCase()")
                btn_type = await btn.get_attribute("type") or ""
                btn_class = await btn.get_attribute("class") or ""
                btn_id = await btn.get_attribute("id") or ""
                btn_name = await btn.get_attribute("name") or ""
                
                if tag_name == "button":
                    btn_text = await btn.inner_text()
                else:
                    btn_text = await btn.get_attribute("value") or ""
                
                info = {
                    "index": i,
                    "tag": tag_name,
                    "type": btn_type,
                    "class": btn_class,
                    "text": btn_text.strip(),
                    "id": btn_id,
                    "name": btn_name,
                }
                button_info.append(info)
                
                if btn_text.strip():  # Only print if has text
                    print(f"\nButton {i}:")
                    print(f"  Tag: {tag_name}")
                    print(f"  Type: {btn_type}")
                    print(f"  Class: {btn_class}")
                    print(f"  Text: {btn_text.strip()}")
                    print(f"  ID: {btn_id}")
                    print(f"  Name: {btn_name}")
            except Exception as e:
                pass
        
        # Find forms
        print("\n--- ALL FORMS ---")
        forms = await page.query_selector_all("form")
        for i, form in enumerate(forms):
            form_action = await form.get_attribute("action") or ""
            form_method = await form.get_attribute("method") or ""
            form_id = await form.get_attribute("id") or ""
            form_class = await form.get_attribute("class") or ""
            
            print(f"\nForm {i}:")
            print(f"  Action: {form_action}")
            print(f"  Method: {form_method}")
            print(f"  ID: {form_id}")
            print(f"  Class: {form_class}")
        
        # Check for DataTables
        print("\n--- CHECKING FOR DATATABLES ---")
        datatables = await page.query_selector_all("table.dataTable, table[id*='dataTable']")
        for i, table in enumerate(datatables):
            table_id = await table.get_attribute("id") or ""
            table_class = await table.get_attribute("class") or ""
            print(f"\nDataTable {i}:")
            print(f"  ID: {table_id}")
            print(f"  Class: {table_class}")
        
        print("\n" + "=" * 80)
        print("STEP 4: TRY SEARCHING FOR GROUP CODE")
        print("=" * 80)
        
        # Try to find and use search box
        search_input = None
        search_selectors_to_try = [
            '.dataTables_filter input',
            'input[type="search"]',
            'input[aria-controls]',
            'input[placeholder*="Search"]',
            'input[placeholder*="search"]',
        ]
        
        for sel in search_selectors_to_try:
            try:
                el = await page.query_selector(sel)
                if el:
                    is_visible = await el.is_visible()
                    if is_visible:
                        search_input = el
                        print(f"\n[FOUND] Search input with selector: {sel}")
                        break
            except:
                pass
        
        if search_input:
            # Try searching for sample codes
            test_codes = ["2UCKG", "GO1TAO"]
            
            for code in test_codes:
                print(f"\nSearching for: {code}")
                await search_input.fill("")
                await asyncio.sleep(0.5)
                await search_input.fill(code)
                await asyncio.sleep(3)
                
                # Take screenshot
                screenshot_name = f"logs/search_results_{code}.png"
                await page.screenshot(path=screenshot_name, full_page=True)
                print(f"Screenshot saved: {screenshot_name}")
                
                # Check for results
                table = await page.query_selector("table")
                if table:
                    rows = await table.query_selector_all("tbody tr")
                    print(f"Found {len(rows)} rows in results")
                    
                    # Get first few rows
                    for i, row in enumerate(rows[:3]):
                        try:
                            row_text = await row.inner_text()
                            print(f"  Row {i}: {row_text[:100]}...")
                        except:
                            pass
                
                # Clear search
                await search_input.fill("")
                await asyncio.sleep(1)
        else:
            print("\n[WARNING] Could not find search input")
        
        print("\n" + "=" * 80)
        print("STEP 5: EXTRACT HTML STRUCTURE")
        print("=" * 80)
        
        # Get search form HTML
        print("\n--- SEARCH FORM HTML ---")
        search_form = await page.query_selector(".dataTables_filter, form, .search-form")
        if search_form:
            form_html = await search_form.inner_html()
            print(form_html[:500])
        
        # Get table HTML structure
        print("\n--- TABLE STRUCTURE ---")
        table = await page.query_selector("table")
        if table:
            # Get table attributes
            table_id = await table.get_attribute("id") or ""
            table_class = await table.get_attribute("class") or ""
            print(f"Table ID: {table_id}")
            print(f"Table Class: {table_class}")
            
            # Get headers
            headers = await table.query_selector_all("thead th")
            print(f"\nTable Headers ({len(headers)} columns):")
            for i, header in enumerate(headers):
                header_text = await header.inner_text()
                print(f"  Column {i}: {header_text}")
            
            # Get first row HTML
            first_row = await table.query_selector("tbody tr")
            if first_row:
                row_html = await first_row.inner_html()
                print(f"\nFirst Row HTML (truncated):")
                print(row_html[:500])
        
        # Save all data to JSON
        try:
            page_title = await page.title()
        except:
            page_title = "[encoding error]"
            
        report = {
            "url": page.url,
            "title": page_title,
            "inputs": input_info,
            "buttons": button_info,
            "search_selector": ".dataTables_filter input" if search_input else None,
        }
        
        with open("logs/travelpackage_inspection.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print("\n" + "=" * 80)
        print("INSPECTION COMPLETE")
        print("=" * 80)
        print("\nData saved to: logs/travelpackage_inspection.json")
        print("\nPress Enter to close the browser...")
        input()
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_travelpackage_page())

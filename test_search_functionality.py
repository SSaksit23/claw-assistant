"""
Script to test the travel package search functionality
"""
import asyncio
import json
import sys
from playwright.async_api import async_playwright

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

async def test_search():
    """Login and test the search functionality."""
    
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
        
        # Login
        print("\nLogging in...")
        await page.goto("https://www.qualityb2bpackage.com/member/login", 
                       wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)
        
        await page.fill('input[name="username"]', 'noi')
        await page.fill('input[name="password"]', 'PrayuthChanocha112')
        await page.click('#btnLogin')
        await asyncio.sleep(5)
        
        if "login" not in page.url.lower():
            print("[SUCCESS] Logged in!")
        else:
            print("[FAILED] Login failed")
            await browser.close()
            return
        
        print("\n" + "=" * 80)
        print("STEP 2: NAVIGATE TO TRAVEL PACKAGE PAGE")
        print("=" * 80)
        
        await page.goto("https://www.qualityb2bpackage.com/travelpackage",
                       wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)
        
        print(f"\nCurrent URL: {page.url}")
        
        # Take initial screenshot
        await page.screenshot(path="logs/travelpackage_initial.png", full_page=True)
        print("Screenshot saved: logs/travelpackage_initial.png")
        
        print("\n" + "=" * 80)
        print("STEP 3: INSPECT SEARCH FORM HTML")
        print("=" * 80)
        
        # Find the search input and surrounding HTML
        search_input = await page.query_selector('#input_search')
        if search_input:
            # Get parent form or container
            parent = await search_input.evaluate("""
                (el) => {
                    let parent = el.parentElement;
                    while (parent && parent.tagName !== 'FORM' && !parent.classList.contains('search-form')) {
                        parent = parent.parentElement;
                        if (parent.tagName === 'BODY') break;
                    }
                    return parent ? parent.outerHTML : el.parentElement.outerHTML;
                }
            """)
            print("\n--- SEARCH FORM/CONTAINER HTML ---")
            print(parent[:1000] if len(parent) > 1000 else parent)
        
        # Find the Go button
        go_button = await page.query_selector('button.btn-go')
        if go_button:
            btn_html = await go_button.evaluate("el => el.outerHTML")
            print("\n--- GO BUTTON HTML ---")
            print(btn_html)
        
        print("\n" + "=" * 80)
        print("STEP 4: TEST SEARCH WITH SAMPLE CODES")
        print("=" * 80)
        
        test_codes = ["2UCKG", "GO1TAO", "2UKWL"]
        
        for code in test_codes:
            print(f"\n--- Searching for: {code} ---")
            
            # Fill search input
            await page.fill('#input_search', code)
            print(f"[OK] Filled search input with: {code}")
            
            # Click Go button
            await page.click('.btn-go')
            print("[OK] Clicked Go button")
            
            # Wait for results
            await asyncio.sleep(4)
            
            # Take screenshot
            screenshot_name = f"logs/search_results_{code}.png"
            await page.screenshot(path=screenshot_name, full_page=True)
            print(f"[OK] Screenshot saved: {screenshot_name}")
            
            # Check table rows
            table = await page.query_selector('table.table-hover')
            if table:
                rows = await table.query_selector_all('tbody tr')
                print(f"[INFO] Found {len(rows)} rows in results table")
                
                # Get first 3 rows
                for i, row in enumerate(rows[:3]):
                    try:
                        cells = await row.query_selector_all('td')
                        if len(cells) >= 3:
                            # Get code and name columns
                            code_cell = await cells[1].inner_text()
                            name_cell = await cells[2].inner_text()
                            print(f"  Row {i+1}:")
                            print(f"    Code: {code_cell.strip()}")
                            print(f"    Name: {name_cell.strip()[:80]}...")
                    except Exception as e:
                        print(f"  Row {i+1}: [error reading row]")
            
            # Clear search for next iteration
            await page.fill('#input_search', '')
            await asyncio.sleep(1)
        
        print("\n" + "=" * 80)
        print("STEP 5: EXTRACT DETAILED HTML STRUCTURE")
        print("=" * 80)
        
        # Do one more search to analyze results
        print("\n--- Searching for '2UKWL' to analyze results ---")
        await page.fill('#input_search', '2UKWL')
        await page.click('.btn-go')
        await asyncio.sleep(4)
        
        # Get table structure
        table = await page.query_selector('table.table-hover')
        if table:
            # Get full table HTML
            table_html = await table.evaluate("el => el.outerHTML")
            
            # Save to file
            with open("logs/table_structure.html", "w", encoding="utf-8") as f:
                f.write(table_html)
            print("[OK] Full table HTML saved to: logs/table_structure.html")
            
            # Get first row for analysis
            first_row = await table.query_selector('tbody tr')
            if first_row:
                row_html = await first_row.evaluate("el => el.outerHTML")
                print("\n--- FIRST ROW HTML ---")
                print(row_html[:800])
                
                # Analyze cells
                cells = await first_row.query_selector_all('td')
                print(f"\n--- CELL ANALYSIS (Total: {len(cells)} cells) ---")
                for i, cell in enumerate(cells):
                    cell_text = await cell.inner_text()
                    cell_class = await cell.get_attribute('class') or ''
                    print(f"Cell {i}: class='{cell_class}', text='{cell_text.strip()[:50]}...'")
        
        # Get filter/dropdown HTML
        print("\n--- FILTER DROPDOWNS HTML ---")
        dropdowns = await page.query_selector_all('.selectpicker')
        for i, dropdown in enumerate(dropdowns[:3]):
            try:
                dropdown_html = await dropdown.evaluate("el => el.outerHTML")
                print(f"\nDropdown {i}:")
                print(dropdown_html[:300])
            except:
                pass
        
        # Create comprehensive report
        report = {
            "search_input": {
                "selector": "#input_search",
                "name": "input_search",
                "id": "input_search",
                "class": "form-control",
                "placeholder": "keyword: ชื่อโปรแกรม หรือ รหัสทัวร์",
                "description": "Main search input for program name or tour code"
            },
            "search_button": {
                "selector": ".btn-go",
                "class": "btn btn-primary btn-go",
                "text": "Go!",
                "description": "Submit button to execute search"
            },
            "results_table": {
                "selector": "table.table-hover",
                "class": "table table-hover",
                "columns": [
                    "#",
                    "รหัส (Code)",
                    "ชื่อโปรแกรมทัวร์ (Program Name)",
                    "รูปแบบโปรแกรมทัวร์ (Program Type)",
                    "ประเภทโปรแกรมทัวร์ (Category)",
                    "โปรแกรมหมดอายุ (Expiry)",
                    "Created",
                    "Edited",
                    "Action"
                ]
            },
            "filters": [
                {"text": "Website", "class": "selectpicker btn-white-cc btn-sm"},
                {"text": "Select Country", "class": "selectpicker btn-white-cc btn-sm"},
                {"text": "Select City", "class": "selectpicker btn-white-cc btn-sm"},
                {"text": "Show", "class": "selectpicker btn-white-cc btn-sm"},
                {"text": "แสดงทั้งหมด", "class": "selectpicker btn-white-cc btn-sm"},
                {"text": "สินค้า b2b", "class": "selectpicker btn-white-cc btn-sm"},
                {"text": "ทั้งหมด", "class": "selectpicker btn-white-cc btn-sm"},
                {"text": "Product By", "class": "selectpicker btn-white-cc btn-sm"},
            ]
        }
        
        with open("logs/search_functionality_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print("\n" + "=" * 80)
        print("ANALYSIS COMPLETE")
        print("=" * 80)
        print("\nFiles created:")
        print("  - logs/travelpackage_initial.png")
        print("  - logs/search_results_2UCKG.png")
        print("  - logs/search_results_GO1TAO.png")
        print("  - logs/search_results_2UKWL.png")
        print("  - logs/table_structure.html")
        print("  - logs/search_functionality_report.json")
        
        print("\n\nPress Enter to close the browser...")
        input()
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_search())

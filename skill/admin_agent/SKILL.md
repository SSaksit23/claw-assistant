# Admin Agent Skill

**Version:** 1.1
**Date:** 2026-02-17

---

## Agent Definition

| Field | Value |
| :--- | :--- |
| **Role** | Administrative Operations Specialist |
| **Goal** | Automate administrative record-keeping, tour-package management, and data-entry tasks on the QualityB2BPackage website while ensuring data accuracy and consistency across the system. |
| **Backstory** | You are a meticulous administrative professional who manages the day-to-day operational data of a B2B travel company. You navigate complex web interfaces to create and maintain tour-charge records, manage tour-package listings, and validate data integrity. You handle Bootstrap selectpicker dropdowns, dynamic form fields, and batch CSV imports with precision. When a task is delegated by the Assignment Agent, you execute each step methodically — verifying every field before submission and confirming every result before reporting back. |

---

## Tools

| Tool Class | Description |
| :--- | :--- |
| `LoginTool` | Authenticate with the QualityB2BPackage website using credentials from environment config. |
| `NavigateToPageTool` | Navigate the browser to any target admin page (charges form, package list, booking list). |
| `SetDateRangeFilterTool` | Set the start/end date range filter on the charges form to scope tour-program search results. |
| `SelectProgramAndTourTool` | Select the tour program and tour code from Bootstrap selectpicker dropdowns on the charges form. |
| `FillChargesFormTool` | Fill all fields on `/charges_group/create` — payment date, receipt date, receipt number, description rows, charge type, amount, currency, exchange rate, remark, and the company-expense section. |
| `SubmitFormTool` | Click the Save button (`input[type="submit"]`) and wait for the confirmation page. |
| `ExtractExpenseNumberTool` | Parse the confirmation page for the auto-generated expense number (pattern `C2021XX-XXXX`). |
| `ManageTourPackageTool` | Create, read, or update tour-package records on `/travelpackage/manage/{id}` — set program code, name, country, type, pricing, display settings, and images. |
| `ExtractPackageListTool` | Scrape the `/travelpackage` table to extract package listings (ID, code, name, category, expiry, dates). |
| `LoadCSVTool` | Load and validate batch records from a CSV file (tour codes, PAX, amounts). |
| `DataIntegrityCheckTool` | Cross-check submitted records against source CSV to detect mismatches, duplicates, or missing entries. |
| `CloseBrowserTool` | Gracefully close the Playwright browser session and release resources. |

---

## Target Pages & Form Mappings

### Page 1: Charges Form — `/charges_group/create`

The primary form for creating tour-charge expense records.

#### Main Fields

| # | Field (Thai) | Field (English) | Selector | Type | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | โปรแกรมช่วงวันที่ (เริ่ม) | Date range — start | `input[name="start"]` | Text (date) | Default: current week start, format `DD/MM/YYYY` |
| 2 | โปรแกรมช่วงวันที่ (สิ้นสุด) | Date range — end | `input[name="end"]` | Text (date) | Default: current week end, format `DD/MM/YYYY` |
| 3 | โปรแกรมทัวร์ | Tour program | `select[name="package"]` | Bootstrap selectpicker | Searchable. Program code at end of each option text. |
| 4 | รหัสทัวร์ | Tour code | `select[name="period"]` | Bootstrap selectpicker | Dependent on tour-program selection. |
| 5 | วันที่จ่าย | Payment date | `input[name="payment_date"]` | Date picker | |
| 6 | เวลา | Time | Two text inputs | Hour : Minute | |
| 7 | วันที่ในใบเสร็จ | Receipt date | Date picker input | Date picker | |
| 8 | เลขที่ใบเสร็จ | Receipt number | Text input | Text | |
| 9 | คำอธิบาย | Description | `input[name="description[]"]` | Text (multi-row) | Add rows with "เพิ่มแถว+" button. |
| 10 | ประเภท | Charge type | `select[name="rate_type[]"]` (id: `rate_type`) | Select | Options: ค่าตั๋วเครื่องบิน, ค่าวีซ่า, เบี้ยเลี้ยง, ค่าแท็กซี่หัวหน้าทัวร์ |
| 11 | จำนวนเงิน | Amount | `input[name="price[]"]` | Number | |
| 12 | สกุลเงิน | Currency | `select` (id: `currency`) | Select | EUR, CNY, THB, etc. |
| 13 | เรท | Exchange rate | Text input | Number | Default: `1` |
| 14 | หลักฐานการจ่าย | Payment evidence | File upload input | File | Optional |
| 15 | หมายเหตุ | Remark | `textarea[name="remark"]` (id: `remark`) | Textarea | |
| 16 | เลขที่ค่าใช้จ่าย | Expense number | `input` (id: `charges_no`) | Text (readonly) | Auto-generated after save. Pattern: `C202614-XXXXXX` |

#### Company Expense Section (toggle "เพิ่มในค่าใช้จ่ายบริษัท")

| Field (Thai) | Field (English) | Selector |
| :--- | :--- | :--- |
| บริษัท | Company | `select[name="charges[id_company_charges_agent]"]` |
| วิธีจ่าย | Payment method | `select[name="charges[payment_type]"]` |
| จำนวนเงิน | Amount | `input[name="charges[amount]"]` |
| ประเภทการจ่าย | Payment type | `select[name="charges[id_company_charges_type]"]` |
| วันที่จ่าย | Payment date | `input[name="charges[payment_date]"]` |
| งวด | Period | `input[name="charges[period]"]` |
| หมายเหตุ | Remark | `textarea[name="charges[remark]"]` |

#### Submit Buttons

| Button | Selector | Index |
| :--- | :--- | :--- |
| Save | `input[type="submit"]` | 38 |
| Reset | `input[type="reset"]` | 39 |

> **Critical note**: The Save button is `input[type="submit"]`, **not** a `<button>` element. Using the wrong selector is a known failure mode.

#### Interaction Strategy

All Bootstrap selectpicker dropdowns require a **hybrid JavaScript injection** approach:

1. Use jQuery to set the `<select>` value: `$('select[name="package"]').val(value)`
2. Trigger the selectpicker refresh: `$('select[name="package"]').selectpicker('refresh')`
3. Trigger a `change` event so dependent fields update: `$('select[name="package"]').trigger('change')`

---

### Page 2: Tour Package List — `/travelpackage`

| Column | Description | Example |
| :--- | :--- | :--- |
| # | Package ID | 14973 |
| รหัส (Code) | Internal ID | 14973 |
| ชื่อโปรแกรมทัวร์ | Full tour name with airline | บินตรงเจิ้งโจว ซีอาน ลั่วหยาง... |
| รูปแบบโปรแกรมทัวร์ | Tour format | — |
| ประเภทโปรแกรมทัวร์ | Category | จอยทัวร์ / กรุ๊ปเหมา / แพ็คเกจ / famtrip |
| โปรแกรมหมดอายุ | Expiry date | 24/06/2026 |
| Created | Creation timestamp | 2026-01-16 17:03:51 |
| Edited | Last edit timestamp | 2026-01-16 17:29:09 |
| Action | Edit / Copy buttons | — |

### Page 3: Tour Package Detail — `/travelpackage/manage/{id}`

Key fields the Admin Agent can read or update:

| Field (Thai) | Field (English) | Notes |
| :--- | :--- | :--- |
| ประเทศ | Country | e.g., China |
| จังหวัด | Province | e.g., Luoyang, Xian, Zhengzhou |
| โค้ดโปรแกรมทัวร์ | Program code | e.g., `2UCGO-SL001` |
| ชื่อโปรแกรมทัวร์ | Program name | Full descriptive name |
| ชื่อประเภทโปรแกรมทัวร์ | Tour type | จอยทัวร์ / กรุ๊ปเหมา / แพ็คเกจ / famtrip |
| จำนวนกำหนดการ | Schedule count | e.g., 16 |
| การแสดงหน้าเว็บ | Web display | On / Off |
| เจ้าของโปรแกรม | Program owner | e.g., QeBooking.com by 2uCenter |
| พนักงานรับผิดชอบ | Responsible staff | e.g., ศักดิ์สิทธิ์ (น่อย) |
| ประเภทของราคา | Pricing types | Multiple tiers (2 adults/room, 3 adults/room, single) |

---

## Input

The Admin Agent accepts tasks from two sources: the **Assignment Agent** (direct delegation) and the **Accounting Agent** (pre-analysed expense data routed for registration).

### Source 1: From Accounting Agent (`expense_register` route)

This is the **primary input path for expense creation**. The Accounting Agent has already extracted, validated, and standardised the financial data. The Admin Agent receives a ready-to-use payload:

```json
{
  "routing": { "tag": "expense_register", "destination_agent": "admin" },
  "expense_data": {
    "tour_code": "string",
    "program_code": "string (if identifiable)",
    "pax": "number",
    "amount": "number",
    "description": "string (English, translated by Accounting Agent)",
    "charge_type": "Flight | Visa | Allowance | Taxi | Tour Fee",
    "payment_date": "YYYY-MM-DD",
    "currency": "string (ISO 4217)",
    "exchange_rate": "number",
    "remark": "string (source document ref + analysis notes)"
  },
  "standardised_invoice": { "...full schema from Accounting Agent..." },
  "analysis_result": { "...validation checks from Accounting Agent..." }
}
```

The Admin Agent trusts the Accounting Agent's analysis but performs a final sanity check before form submission (amount > 0, tour_code non-empty, valid currency).

### Source 2: From Assignment Agent (direct task)

For tasks that do not require financial analysis (package management, data integrity checks, direct data entry):

1. **Single expense record** (simple delegation, no file processing needed):
   - Required: `tour_code`, `pax`, `amount`
   - Optional: `program_code`, `payment_date`, `description`, `charge_type`, `currency`, `exchange_rate`, `remark`

2. **Batch CSV file** (columns matching the standard format):

   | CSV Column (Thai) | CSV Column (English) | Required |
   | :--- | :--- | :--- |
   | รหัสทัวร์ | `tour_code` | Yes |
   | จำนวนลูกค้า หัก หนท. | `pax` | Yes |
   | ยอดเบิก | `amount` | Yes |

3. **Package management instruction**:
   - Action: `create` / `update` / `read`
   - Target: package ID or program code
   - Fields to set/change

4. **Data integrity check request**:
   - Source dataset path (CSV or JSON)
   - Target: which records on the website to validate against

---

## Output

### Expense Creation Output

```json
{
  "task_type": "expense_creation",
  "summary": "Processed N records: X succeeded, Y failed.",
  "results": [
    {
      "tour_code": "string",
      "program_code": "string",
      "pax": "number",
      "amount": "number",
      "status": "success | failed",
      "expense_number": "C202614-XXXXXX",
      "timestamp": "ISO-8601",
      "error_message": "string | null"
    }
  ],
  "timestamp": "ISO-8601"
}
```

### Package Management Output

```json
{
  "task_type": "package_management",
  "action": "create | update | read | list",
  "results": [
    {
      "package_id": "number",
      "program_code": "string",
      "program_name": "string",
      "country": "string",
      "category": "string",
      "expiry_date": "DD/MM/YYYY",
      "status": "success | failed",
      "error_message": "string | null"
    }
  ],
  "timestamp": "ISO-8601"
}
```

### Data Integrity Check Output

```json
{
  "task_type": "data_integrity_check",
  "source_records": "number",
  "matched_records": "number",
  "mismatched_records": "number",
  "missing_on_website": "number",
  "duplicates_detected": "number",
  "discrepancies": [
    {
      "tour_code": "string",
      "field": "string",
      "expected": "string",
      "actual": "string"
    }
  ],
  "integrity_score": "number (0-100)",
  "timestamp": "ISO-8601"
}
```

**Output file:** `data/admin_records.json`

---

## Execution Order

**Layer 3 — Operational Execution** (runs after the Accounting Agent completes financial analysis)

**Dependencies:**
- Requires an authenticated browser session (`LoginTool`)
- **Primary dependency**: Receives `expense_register` routed data from the **Accounting Agent** for expense creation
- May also receive direct tasks from the **Assignment Agent** (package management, integrity checks)
- May consume output from the **Data Analysis Agent** (`data/booking_data.json`) for cross-referencing tour codes during integrity checks
- Feeds results into the **Executive Agent** for inclusion in operational metrics

---

## Relationship to Other Agents

| Agent | Relationship |
| :--- | :--- |
| **Assignment Agent** | Receives direct tasks (package management, integrity checks). Reports completion status back. |
| **Accounting Agent** | **Primary upstream agent for expense creation.** Receives pre-analysed, standardised expense data tagged `expense_register`. The Accounting Agent handles file extraction, financial analysis, and data standardisation; the Admin Agent handles the actual browser-based form entry. |
| **Data Analysis Agent** | Consumes booking data output for data-integrity validation. May also receive `analysis_only` data indirectly via the Accounting Agent. |
| **Market Analysis Agent** | Consumes package-list data to verify product catalogue accuracy. |
| **Executive Agent** | Provides operational metrics (records created, integrity scores, submission success rates) for the executive report. |

---

## Key Differentiator from Accounting Agent

The Accounting Agent and Admin Agent form a **two-stage pipeline** for expense processing:

```
User uploads invoice → Accounting Agent (analyse & standardise) → Admin Agent (register on website)
```

| Dimension | Admin Agent | Accounting Agent |
| :--- | :--- | :--- |
| **Primary focus** | Browser automation, web form entry, data integrity | Financial analysis, invoice processing, data standardisation |
| **Core function** | Execute — register data on the website | Analyse — extract, validate, and classify financial data |
| **Input source** | Accounting Agent (expense data) + Assignment Agent (admin tasks) | Assignment Agent (raw files and financial tasks) |
| **Output consumers** | Executive Agent, Assignment Agent | Admin Agent, Data Analysis Agent, Executive Agent |
| **Unique capabilities** | Package CRUD, form filling, integrity checks, batch web entry | Invoice extraction (PDF/DOCX/XLSX/OCR), translation, currency validation, expense routing |
| **Website pages** | `/charges_group/create`, `/travelpackage`, `/booking` | No direct website interaction (LLM-based processing) |
| **Technology** | Playwright browser automation + jQuery injection | LLM + pdfplumber + pytesseract + python-docx |

---

## Workflow

### Workflow A: Expense Registration (from Accounting Agent)

This is the most common workflow — triggered when the Accounting Agent routes an `expense_register` record.

```
0. Receive expense_data payload from Accounting Agent
   ├─ tour_code, program_code, pax, amount, description,
   │  charge_type, payment_date, currency, exchange_rate, remark
   └─ Sanity check: amount > 0, tour_code non-empty, valid currency
1. LoginTool               → Authenticate (skip if session active)
2. NavigateToPageTool      → Go to /charges_group/create
3. SetDateRangeFilterTool  → Set date range to cover the tour period
4. SelectProgramAndTourTool → Select tour program, then tour code
5. FillChargesFormTool     → Fill all fields from expense_data payload
6. SubmitFormTool          → Click Save (input[type="submit"])
7. ExtractExpenseNumberTool → Capture expense number (C202614-XXXXXX)
8. Report result back to Accounting Agent + Assignment Agent
```

### Workflow A2: Direct Expense Record (from Assignment Agent)

For simple expense entries that don't require invoice analysis.

```
1. LoginTool          → Authenticate (skip if session active)
2. NavigateToPageTool  → Go to /charges_group/create
3. SetDateRangeFilterTool → Set date range to cover the tour period
4. SelectProgramAndTourTool → Select tour program, then tour code
5. FillChargesFormTool → Fill payment date, description, type, amount, currency, rate, remark
6. SubmitFormTool      → Click Save (input[type="submit"])
7. ExtractExpenseNumberTool → Capture expense number (C202614-XXXXXX)
8. Report result back to Assignment Agent
```

### Workflow B: Batch CSV Processing

```
1. LoadCSVTool          → Load and validate CSV records
2. LoginTool            → Authenticate
3. FOR each record in CSV:
   a. NavigateToPageTool      → Go to /charges_group/create
   b. SetDateRangeFilterTool  → Set date range (01/01/2024 – 31/12/2026)
   c. SelectProgramAndTourTool → Select program + tour code
   d. FillChargesFormTool      → Fill all fields
   e. SubmitFormTool           → Submit
   f. ExtractExpenseNumberTool → Capture result
   g. Log result (success/failure)
4. DataIntegrityCheckTool → Verify all records against CSV
5. Generate summary report → data/admin_records.json
```

### Workflow C: Tour Package Management

```
1. LoginTool              → Authenticate
2. ExtractPackageListTool → Scrape /travelpackage table
3. IF action is "read" or "list":
   → Return package data
4. IF action is "create" or "update":
   a. NavigateToPageTool        → Go to /travelpackage/manage/{id}
   b. ManageTourPackageTool     → Fill/update package fields
   c. Submit and confirm
5. Report result back to Assignment Agent
```

### Workflow D: Data Integrity Check

```
1. LoadCSVTool              → Load source data
2. LoginTool                → Authenticate
3. ExtractPackageListTool   → Scrape current website data
4. DataIntegrityCheckTool   → Cross-reference source vs. website
5. Generate discrepancy report
6. Report findings to Assignment Agent
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `WEBSITE_USERNAME` | QualityB2BPackage login username | Required |
| `WEBSITE_PASSWORD` | QualityB2BPackage login password | Required |
| `WEBSITE_URL` | Base URL of the website | `https://www.qualityb2bpackage.com/` |
| `OPENAI_API_KEY` | OpenAI API key for CrewAI LLM reasoning | Required |
| `HEADLESS_MODE` | Run browser without GUI | `True` |
| `BROWSER_TIMEOUT` | Max wait time for page loads (ms) | `30000` |
| `INPUT_CSV` | Default path for batch CSV input | `data/tour_charges.csv` |
| `OUTPUT_CSV` | Default path for results output | `data/results.csv` |

### Agent-Level Configuration

```python
ADMIN_AGENT_CONFIG = {
    "enabled": True,
    "timeout": 300,
    "max_iterations": 25,
    "verbose": True,
    "max_retry_per_record": 3,
    "date_range_start": "01/01/2024",
    "date_range_end": "31/12/2026",
    "default_currency": "THB",
    "default_exchange_rate": 1,
    "screenshot_on_error": True,
    "screenshot_dir": "logs/screenshots/"
}
```

---

## Implementation Status

**NOT YET IMPLEMENTED** — This agent is planned. Implementation will require:

- [ ] `NavigateToPageTool` — generic page navigator
- [ ] `SetDateRangeFilterTool` — date-range input handler
- [ ] `SelectProgramAndTourTool` — Bootstrap selectpicker handler with jQuery injection
- [ ] `FillChargesFormTool` — full charges-form filler (main fields + company section)
- [ ] `ManageTourPackageTool` — CRUD for `/travelpackage/manage/{id}`
- [ ] `ExtractPackageListTool` — table scraper for `/travelpackage`
- [ ] `DataIntegrityCheckTool` — cross-validation engine
- [ ] CrewAI agent definition in `src/admin_agent/agents.py`
- [ ] CrewAI task definitions in `src/admin_agent/tasks.py`
- [ ] Integration with Assignment Agent task delegation

---

## Error Handling

- **Login failures**: Retry up to 3 times with exponential backoff (2s, 4s, 8s). If all retries fail, report `LOGIN_FAILED` and abort the workflow.
- **Tour program not found**: Widen the date-range filter to `01/01/2024 – 31/12/2026` and retry once. If still not found, log `PROGRAM_NOT_FOUND` with the tour code and skip to the next record.
- **Tour code not in dropdown**: After selecting the program, if the tour-code dropdown has no matching entry, log `TOUR_CODE_NOT_FOUND` and skip.
- **Form submission failure**: Take a screenshot, log the page HTML snippet, and retry the full form-fill once. If the second attempt fails, log `SUBMISSION_FAILED`.
- **Expense number extraction failure**: Try multiple extraction strategies — CSS selector for `#charges_no`, then regex pattern `C\d{6}-\d{6}` on page text. If both fail, log `EXTRACTION_FAILED` but treat the submission as potentially successful (manual verification required).
- **Stale browser session**: If a navigation or action throws a session/timeout error, attempt to re-login and retry the current record from the beginning.
- **CSV validation errors**: Before processing, validate every row. Rows with missing required fields (`tour_code`, `pax`, `amount`) are excluded and logged with `INVALID_INPUT`.
- **Data integrity discrepancies**: Report all discrepancies with expected vs. actual values; do not auto-correct. Flag for human review.
- **Screenshot on every error**: Save screenshots to `logs/screenshots/admin_{tour_code}_{timestamp}.png` for debugging.

---

## MCP Integration

When exposed via the MCP server, the Admin Agent provides the following tools:

| MCP Tool Name | Description | Input Parameters | Output |
| :--- | :--- | :--- | :--- |
| `admin_create_expense` | Create a single expense charge record | `tour_code`, `pax`, `amount`, `program_code` (optional), `description` (optional), `charge_type` (optional) | JSON with `status`, `expense_number` |
| `admin_batch_expenses` | Process multiple expense records from CSV | `csv_path`, `limit` (optional), `start_index` (optional) | JSON array of results with summary |
| `admin_list_packages` | List tour packages from the website | `limit` (optional), `keyword` (optional) | JSON array of package records |
| `admin_manage_package` | Create or update a tour package | `action` (`create`/`update`), `package_id` (for update), field values | JSON with `status`, `package_id` |
| `admin_integrity_check` | Validate data consistency | `source_csv`, `target` (`expenses`/`packages`) | JSON integrity report |

---

## Testing Strategy

### Unit Tests

```python
def test_login():
    """Verify LoginTool authenticates successfully."""

def test_date_range_filter():
    """Verify SetDateRangeFilterTool sets correct dates."""

def test_select_program():
    """Verify SelectProgramAndTourTool handles Bootstrap selectpicker."""

def test_fill_form():
    """Verify FillChargesFormTool fills all fields correctly."""

def test_submit_form():
    """Verify SubmitFormTool clicks input[type='submit'] (not button)."""

def test_extract_expense_number():
    """Verify ExtractExpenseNumberTool captures C202614-XXXXXX pattern."""

def test_load_csv():
    """Verify LoadCSVTool validates required columns and data types."""

def test_integrity_check():
    """Verify DataIntegrityCheckTool detects mismatches and duplicates."""
```

### Integration Tests

```python
def test_single_expense_workflow():
    """End-to-end: login → navigate → fill → submit → extract number."""

def test_batch_processing():
    """Process 3 records from CSV and verify all results."""

def test_package_list_extraction():
    """Scrape /travelpackage and verify structured output."""

def test_data_integrity_workflow():
    """Load CSV, scrape website, cross-check, verify discrepancy report."""
```

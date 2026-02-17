# Accounting Agent Skill

**Version:** 2.0
**Date:** 2026-02-17

---

## Agent Definition

| Field | Value |
| :--- | :--- |
| **Role** | Financial Intelligence Specialist |
| **Goal** | Receive financial documents from the Assignment Agent, perform detailed financial analysis (price verification, date validation, currency checks), standardise the data into a structured format, and route the results — either to the Admin Agent for expense registration or to the Data Analysis Agent for further reporting. |
| **Backstory** | You are a senior financial analyst with deep expertise in travel-industry accounting. You receive invoices, receipts, and confirmations in multiple formats (PDF, DOCX, XLSX, images) and multiple languages (Thai, Chinese, English). You extract every financial detail with precision, cross-check totals against line items, flag discrepancies, translate descriptions into English, and produce a clean, standardised JSON record. You never submit data downstream without verifying its integrity first. |

---

## Core Workflow (4 Steps)

```
┌──────────────────────────────────────────────────────────────────┐
│  Step 1: RECEIVE                                                 │
│  ← Assignment Agent sends file (PDF/DOCX/XLSX/image) or data    │
└──────────────────┬───────────────────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  Step 2: ANALYSE                                                 │
│  Extract raw text → validate prices, dates, currencies, totals   │
│  Detect anomalies (mismatched totals, missing fields, bad dates) │
└──────────────────┬───────────────────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  Step 3: DEFINE                                                  │
│  Map extracted data to Standardised Invoice JSON Schema           │
│  Translate descriptions → English                                │
│  Classify expense type and assign routing tag                    │
└──────────────────┬───────────────────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  Step 4: ROUTE                                                   │
│  ┌─ expense_register  → Admin Agent (charge record creation)     │
│  └─ analysis_only     → Data Analysis Agent (reporting/BI)       │
└──────────────────────────────────────────────────────────────────┘
```

---

## Tools

| Tool Class | Description |
| :--- | :--- |
| **Step 1 — Receive** | |
| `ReceiveDocumentTool` | Accept a file path or binary payload from the Assignment Agent. Detect file type (PDF, DOCX, XLSX, PNG/JPG). |
| **Step 2 — Analyse** | |
| `ExtractTextTool` | Extract raw text from the document. Uses `pdfplumber` for PDF, `python-docx` for DOCX, `openpyxl` for XLSX, and `pytesseract` OCR for images. |
| `FinancialAnalysisTool` | Use the LLM to parse extracted text and perform financial checks: verify line-item totals match the grand total, validate date ranges, confirm currency codes, detect duplicate charges, and flag anomalies. |
| `CurrencyValidationTool` | Validate currency codes against ISO 4217, check exchange rates against reference rates, and flag suspicious conversions. |
| **Step 3 — Define** | |
| `StandardiseInvoiceTool` | Map extracted data to the Standardised Invoice JSON Schema (see schema below). Fill all required fields, set missing fields to defaults. |
| `TranslateFieldsTool` | Use the LLM to translate all descriptive text fields (descriptions, notes, activity details) into English while preserving the JSON structure. |
| `ClassifyExpenseTool` | Classify the document type and determine the routing tag: `expense_register` (needs to be recorded on the website) or `analysis_only` (informational, for reporting). |
| **Step 4 — Route** | |
| `RouteToAdminTool` | Package the standardised JSON and send it to the **Admin Agent** for expense registration on `/charges_group/create`. |
| `RouteToAnalysisTool` | Package the standardised JSON and send it to the **Data Analysis Agent** for inclusion in booking/financial reports. |
| `SaveFinancialRecordTool` | Persist the analysis results and standardised data to `data/financial_records.json`. |

---

## Step-by-Step Detail

### Step 1: Receive

The Accounting Agent is activated when the **Assignment Agent** delegates a financial task. Input arrives as:

| Input Type | Description | Example |
| :--- | :--- | :--- |
| **File upload** | A document attached via LINE message, forwarded by the Assignment Agent | Invoice PDF, confirmation DOCX, receivables XLSX, receipt image |
| **Structured data** | A JSON object from another agent or from a CSV import | `{ "tour_code": "...", "amount": ..., "pax": ... }` |
| **Text message** | A natural-language financial instruction from the user | "Register expense 5000 THB for tour JAPAN7N-001" |

**Actions:**
1. Detect the input type (file vs. structured data vs. text)
2. If file → determine format (PDF/DOCX/XLSX/image) and queue for extraction
3. If structured data → skip extraction, proceed directly to analysis
4. If text → use LLM to parse intent and extract parameters

---

### Step 2: Analyse (Financial Analysis)

This is the intelligence core. The agent examines every financial detail in the document.

#### 2.1 Text Extraction

| File Format | Extraction Method | Library |
| :--- | :--- | :--- |
| PDF (text-based) | Direct text extraction | `pdfplumber` |
| PDF (image-based) | OCR → text | `pytesseract` |
| DOCX | Paragraph + table extraction | `python-docx` |
| XLSX | Cell-by-cell extraction with formula resolution | `openpyxl` |
| PNG / JPG | OCR → text | `pytesseract` |

#### 2.2 Financial Validation Checks

| Check | Description | Flag Level |
| :--- | :--- | :--- |
| **Line-item total** | Sum of `quantity × unit_price` for each item must equal `total_price` | ERROR if mismatch > 1% |
| **Grand total** | Sum of all line-item totals must equal `subtotal`; `subtotal + tax = grand_total` | ERROR if mismatch |
| **Date validity** | All dates must be parseable and logically ordered (issue_date ≤ start_date ≤ end_date) | WARNING if illogical |
| **Date format** | Convert all dates to `YYYY-MM-DD` regardless of source format | AUTO-FIX |
| **Currency code** | Must be a valid ISO 4217 code (THB, RMB, USD, EUR, CNY, etc.) | ERROR if unrecognised |
| **Exchange rate** | If multi-currency, exchange rate must be > 0 and within reasonable bounds | WARNING if suspicious |
| **PAX count** | `adults + children + escorts = total_pax` | WARNING if mismatch |
| **Duplicate detection** | Check if same `tour_code + amount + date` exists in `data/financial_records.json` | WARNING if duplicate found |
| **Required fields** | `tour_code` or `tour_name`, `grand_total`, `currency` must be present | ERROR if missing |
| **Payment deadline** | Flag if payment deadline is in the past or within 24 hours | WARNING |

#### 2.3 Analysis Output

```json
{
  "analysis_status": "passed | warnings | errors",
  "total_checks": "number",
  "passed_checks": "number",
  "warnings": [
    {
      "check": "string",
      "field": "string",
      "message": "string",
      "expected": "string",
      "actual": "string"
    }
  ],
  "errors": [
    {
      "check": "string",
      "field": "string",
      "message": "string",
      "expected": "string",
      "actual": "string"
    }
  ]
}
```

---

### Step 3: Define (Standardise & Classify)

#### 3.1 Standardised Invoice JSON Schema

The agent maps all extracted data into this unified schema, designed for travel-industry invoices:

```json
{
  "document_info": {
    "document_title": "string",
    "document_type": "Confirmation | Invoice | Quote | Summary Statement | Receipt",
    "issue_date": "YYYY-MM-DD",
    "internal_ref_id": "string",
    "external_ref_id": "string"
  },
  "supplier": {
    "company_name": "string",
    "contact_person": "string",
    "phone": "string",
    "email": "string",
    "address": "string"
  },
  "customer": {
    "company_name": "string",
    "contact_person": "string",
    "phone": "string",
    "email": "string",
    "address": "string",
    "source_market": "string"
  },
  "tour_details": {
    "tour_name": "string",
    "tour_code": "string",
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "duration_days": "number",
    "participants": {
      "adults": "number",
      "children": "number",
      "tour_escorts": "number",
      "total_pax": "number"
    },
    "service_standards": {
      "accommodation_standard": "string",
      "meal_plan": "string",
      "transportation_mode": "string",
      "guide_notes": "string",
      "insurance_notes": "string"
    },
    "itinerary": [
      {
        "day_number": "number",
        "date": "YYYY-MM-DD",
        "transportation": "string",
        "activities": "string (translated to English)",
        "meals": {
          "breakfast": "boolean",
          "lunch": "boolean",
          "dinner": "boolean"
        },
        "accommodation": "string"
      }
    ]
  },
  "financials": {
    "currency": "string (ISO 4217)",
    "line_items": [
      {
        "item_id": "string",
        "description": "string (translated to English)",
        "item_type": "Flight | Accommodation | Tour Fee | Visa | Tip | Allowance | Taxi | Adjustment",
        "quantity": "number",
        "unit_price": "number",
        "total_price": "number",
        "currency": "string",
        "notes": "string"
      }
    ],
    "subtotal": "number",
    "tax_amount": "number",
    "grand_total": "number",
    "total_in_words": "string",
    "payment_summary": {
      "amount_receivable": "number",
      "amount_collected": "number",
      "amount_paid": "number",
      "amount_outstanding": "number"
    }
  },
  "payment_details": {
    "payment_deadline": "YYYY-MM-DD HH:MM:SS",
    "payment_terms": "string",
    "bank_accounts": [
      {
        "account_name": "string",
        "account_number": "string",
        "bank_name": "string",
        "bank_branch": "string",
        "currency": "string",
        "country": "string",
        "notes": "string"
      }
    ]
  },
  "confirmation_details": {
    "requires_signature": "boolean",
    "confirmation_status": "Pending | Confirmed",
    "confirmation_request_text": "string",
    "signatories": [
      {
        "party": "Supplier | Customer",
        "company_name": "string",
        "signer_name": "string",
        "date": "YYYY-MM-DD"
      }
    ]
  },
  "raw_text": "string (full extracted text for audit)"
}
```

#### 3.2 Translation Rules

| Source Language | Fields Translated | Target Language |
| :--- | :--- | :--- |
| Chinese (中文) | descriptions, activities, notes, payment terms | English |
| Thai (ไทย) | descriptions, activities, notes, payment terms | English |
| Mixed | All non-English descriptive fields | English |

The JSON structure and field names remain unchanged — only the **values** of descriptive fields are translated.

#### 3.3 Expense Classification & Routing Tag

| Document Type | Contains Actionable Expense? | Routing Tag | Destination Agent |
| :--- | :--- | :--- | :--- |
| Invoice with specific tour charge | Yes — needs to be registered as expense on website | `expense_register` | **Admin Agent** |
| Receipt / proof of payment | Yes — may need recording | `expense_register` | **Admin Agent** |
| Confirmation (no payment yet) | No — informational only | `analysis_only` | **Data Analysis Agent** |
| Summary Statement / Receivables | No — for reporting | `analysis_only` | **Data Analysis Agent** |
| Quote / Estimate | No — for budgeting | `analysis_only` | **Data Analysis Agent** |

The routing tag is embedded in the output:

```json
{
  "routing": {
    "tag": "expense_register | analysis_only",
    "destination_agent": "admin | data_analysis",
    "reason": "string (why this routing was chosen)",
    "priority": "high | medium | low"
  }
}
```

---

### Step 4: Route

Based on the routing tag, the agent delivers the standardised JSON to the appropriate downstream agent.

#### Route A: To Admin Agent (`expense_register`)

The Accounting Agent extracts the fields the Admin Agent needs for the charges form:

```json
{
  "routing": { "tag": "expense_register", "destination_agent": "admin" },
  "expense_data": {
    "tour_code": "string (from tour_details.tour_code)",
    "program_code": "string (if identifiable)",
    "pax": "number (from tour_details.participants.total_pax)",
    "amount": "number (from financials.grand_total)",
    "description": "string (summary of line items)",
    "charge_type": "string (mapped from line_items.item_type)",
    "payment_date": "YYYY-MM-DD",
    "currency": "string",
    "exchange_rate": "number",
    "remark": "string (source document ref + analysis notes)"
  },
  "standardised_invoice": { "...full schema..." },
  "analysis_result": { "...validation checks..." }
}
```

#### Route B: To Data Analysis Agent (`analysis_only`)

```json
{
  "routing": { "tag": "analysis_only", "destination_agent": "data_analysis" },
  "standardised_invoice": { "...full schema..." },
  "analysis_result": { "...validation checks..." },
  "financial_highlights": {
    "grand_total": "number",
    "currency": "string",
    "tour_code": "string",
    "supplier": "string",
    "customer": "string",
    "date_range": "YYYY-MM-DD to YYYY-MM-DD",
    "pax_count": "number"
  }
}
```

#### Both Routes: Save to Local Record

Regardless of routing, every processed document is persisted:

**Output file:** `data/financial_records.json`

---

## Complete Output Schema

```json
{
  "task_id": "string (UUID)",
  "source_file": "string (original filename)",
  "source_type": "pdf | docx | xlsx | image | structured_data | text",
  "processing_steps": {
    "received_at": "ISO-8601",
    "extraction_completed_at": "ISO-8601",
    "analysis_completed_at": "ISO-8601",
    "standardisation_completed_at": "ISO-8601",
    "routed_at": "ISO-8601"
  },
  "analysis_result": {
    "analysis_status": "passed | warnings | errors",
    "total_checks": "number",
    "passed_checks": "number",
    "warnings": [],
    "errors": []
  },
  "standardised_invoice": { "...full Standardised Invoice JSON Schema..." },
  "routing": {
    "tag": "expense_register | analysis_only",
    "destination_agent": "admin | data_analysis",
    "reason": "string",
    "priority": "high | medium | low"
  },
  "expense_data": { "...if routed to admin..." },
  "financial_highlights": { "...if routed to data_analysis..." },
  "timestamp": "ISO-8601"
}
```

---

## Input

The Accounting Agent accepts tasks exclusively from the **Assignment Agent**. Input types:

| Input Type | Format | Required Fields | Example |
| :--- | :--- | :--- | :--- |
| Invoice file | PDF, DOCX, XLSX, PNG, JPG | File path or binary | `/uploads/invoice_xinjiang_260118.pdf` |
| Structured data | JSON | `tour_code`, `amount` (minimum) | `{ "tour_code": "2UKWL3NN", "amount": 123120, "currency": "RMB" }` |
| Text instruction | Natural language | Must mention financial context | "Register 5000 THB expense for JAPAN7N-001" |
| CSV batch | CSV file | `tour_code`, `pax`, `amount` columns | `data/tour_charges.csv` |

---

## Execution Order

**Layer 2 — Financial Intelligence** (runs after Data Analysis Agent completes Layer 1)

**Dependencies:**
- Receives tasks from the **Assignment Agent**
- May receive supplementary booking data from the **Data Analysis Agent** for cross-referencing

**Downstream consumers:**
- **Admin Agent** — receives `expense_register` tagged records for website data entry
- **Data Analysis Agent** — receives `analysis_only` tagged records for reporting
- **Executive Agent** — consumes `data/financial_records.json` for financial summaries

---

## Relationship to Other Agents

| Agent | Relationship |
| :--- | :--- |
| **Assignment Agent** | Receives all financial tasks from Assignment Agent. Reports processing status back. |
| **Admin Agent** | Sends `expense_register` records with pre-filled expense data for web form entry. The Admin Agent handles the actual browser automation on `/charges_group/create`. |
| **Data Analysis Agent** | Sends `analysis_only` records for inclusion in booking and financial reports. May receive booking data for cross-referencing tour codes. |
| **Market Analysis Agent** | No direct interaction. Financial data flows to Market Analysis via the Executive Agent. |
| **Executive Agent** | Provides financial summaries, analysis results, and processed invoice counts for the executive report. |

---

## Configuration

### Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `OPENAI_API_KEY` | OpenAI API key for LLM extraction, analysis, and translation | Required |
| `OPENAI_MODEL` | LLM model for financial analysis | `gpt-4o-mini` |
| `TESSERACT_PATH` | Path to Tesseract OCR binary (for image processing) | System default |
| `FINANCIAL_RECORDS_PATH` | Path to persist processed records | `data/financial_records.json` |
| `UPLOAD_DIR` | Directory for received document files | `uploads/` |
| `TRANSLATION_TARGET` | Target language for translated fields | `en` |

### Agent-Level Configuration

```python
ACCOUNTING_AGENT_CONFIG = {
    "enabled": True,
    "timeout": 300,
    "max_iterations": 20,
    "verbose": True,
    "llm_model": "gpt-4o-mini",
    "translation_enabled": True,
    "translation_target_language": "en",
    "validation_strict_mode": False,
    "duplicate_check_enabled": True,
    "max_file_size_mb": 25,
    "supported_formats": ["pdf", "docx", "xlsx", "png", "jpg", "jpeg", "csv"],
    "anomaly_threshold_percent": 1.0
}
```

---

## Implementation Status

**PARTIALLY IMPLEMENTED** — Core extraction and standardisation logic exists in the `auto-receipt` project:
- `backend/extractors.py` — File text extraction (PDF, DOCX, XLSX)
- `backend/llm_processor.py` — OpenAI integration for standardisation
- `backend/schemas.py` — Pydantic models for the invoice schema
- `backend/main.py` — FastAPI endpoints for upload and processing

**Still needed:**
- [ ] `FinancialAnalysisTool` — price/date/currency validation checks
- [ ] `CurrencyValidationTool` — ISO 4217 validation and exchange-rate checking
- [ ] `ClassifyExpenseTool` — routing logic (expense_register vs. analysis_only)
- [ ] `RouteToAdminTool` — integration with Admin Agent
- [ ] `RouteToAnalysisTool` — integration with Data Analysis Agent
- [ ] `SaveFinancialRecordTool` — persistent record storage
- [ ] CrewAI agent definition in `src/accounting_agent/agents.py`
- [ ] CrewAI task definitions in `src/accounting_agent/tasks.py`
- [ ] Integration with Assignment Agent task delegation

---

## Error Handling

- **File format not supported**: Return `UNSUPPORTED_FORMAT` error with the detected MIME type. Do not attempt processing.
- **Text extraction failure**: If `pdfplumber` fails, fall back to `pytesseract` OCR. If OCR also fails, return `EXTRACTION_FAILED` with the error detail.
- **LLM parsing failure**: If the LLM returns malformed JSON or fails to extract required fields, retry once with a more explicit prompt. If the second attempt fails, return `STANDARDISATION_FAILED`.
- **Financial validation errors**: Do **not** block routing on warnings. Only block on critical errors (missing `grand_total`, unrecognisable currency). Attach all warnings/errors to the output so downstream agents are aware.
- **Duplicate detection**: If a potential duplicate is found, attach a `DUPLICATE_WARNING` but still process and route. Let the destination agent decide whether to proceed.
- **Translation failure**: If translation fails for a field, keep the original text and add a `TRANSLATION_FAILED` flag for that field.
- **Routing failure**: If the destination agent is unavailable, save the record to `data/financial_records.json` with status `PENDING_ROUTING` and retry on the next cycle.
- **File too large**: If the file exceeds `max_file_size_mb`, return `FILE_TOO_LARGE` without processing.

---

## MCP Integration

When exposed via the MCP server, the Accounting Agent provides:

| MCP Tool Name | Description | Input Parameters | Output |
| :--- | :--- | :--- | :--- |
| `accounting_process_invoice` | Process a single invoice document through the full 4-step pipeline | `file_path`, `translation` (optional, default `true`) | Full output JSON with analysis, standardised data, and routing |
| `accounting_analyse_file` | Extract and analyse only (steps 1-2), without standardising or routing | `file_path` | Analysis result with extracted text and validation checks |
| `accounting_standardise` | Standardise pre-extracted text into the JSON schema (step 3 only) | `raw_text`, `source_type` | Standardised Invoice JSON |
| `accounting_check_status` | Check processing status of a previously submitted task | `task_id` | Status and result if completed |

---

## Testing Strategy

### Unit Tests

```python
def test_extract_text_pdf():
    """Verify ExtractTextTool handles text-based PDFs."""

def test_extract_text_docx():
    """Verify ExtractTextTool handles DOCX with tables."""

def test_extract_text_xlsx():
    """Verify ExtractTextTool handles multi-sheet XLSX."""

def test_extract_text_image_ocr():
    """Verify ExtractTextTool handles image-based documents via OCR."""

def test_financial_analysis_valid():
    """Verify FinancialAnalysisTool passes a clean invoice."""

def test_financial_analysis_mismatched_totals():
    """Verify FinancialAnalysisTool flags line-item vs. grand-total mismatch."""

def test_financial_analysis_invalid_dates():
    """Verify FinancialAnalysisTool flags illogical date ranges."""

def test_standardise_invoice():
    """Verify StandardiseInvoiceTool produces valid JSON matching the schema."""

def test_translate_fields():
    """Verify TranslateFieldsTool translates Chinese/Thai to English."""

def test_classify_expense_register():
    """Verify ClassifyExpenseTool tags invoices as expense_register."""

def test_classify_analysis_only():
    """Verify ClassifyExpenseTool tags confirmations as analysis_only."""

def test_route_to_admin():
    """Verify RouteToAdminTool packages expense_data correctly."""

def test_route_to_analysis():
    """Verify RouteToAnalysisTool packages financial_highlights correctly."""
```

### Integration Tests

```python
def test_full_pipeline_invoice_pdf():
    """End-to-end: PDF invoice → extract → analyse → standardise → route to admin."""

def test_full_pipeline_confirmation_docx():
    """End-to-end: DOCX confirmation → extract → analyse → standardise → route to data_analysis."""

def test_full_pipeline_receivables_xlsx():
    """End-to-end: XLSX receivables → extract → analyse → standardise → route to data_analysis."""

def test_batch_csv_processing():
    """Process CSV of tour charges → standardise each → route all to admin."""
```

"""
Document Parser Service.

Parses uploaded files (CSV, Excel, PDF, DOCX, text) and extracts
structured expense data: group code, travel date, size, price, etc.

Uses OpenAI for unstructured text extraction when the file format
is not a simple table (e.g., PDF or DOCX with free-form text).
"""

import os
import re
import json
import logging
from typing import Optional

import pandas as pd
from openai import OpenAI

from config import Config

logger = logging.getLogger(__name__)


EXPENSE_FIELDS = {
    "tour_code": "Tour/group code (e.g., GO1TAO5NTAOQW260304)",
    "program_code": "Program code for the travel program",
    "travel_date": "Travel date or date range (e.g., 0304-0309 or 10-13 Mar)",
    "pax": "Number of passengers / group size",
    "unit_price": "Price per person/unit",
    "amount": "Total expense amount (unit_price x pax)",
    "currency": "Detected currency (CNY, THB, USD, etc.)",
    "supplier_name": "Supplier / company name (Party A / 甲方)",
    "description": "Description of the expense (flight route, service name, etc.)",
    "charge_type": "Type: flight, land_tour, single_supplement, service_fee, guide_tip, visa, accommodation, meal, transport, insurance, entrance_fee, other",
}


def parse_file(file_path: str) -> dict:
    """
    Parse any supported file and extract expense records.

    Returns:
        {
            "status": "success" | "error",
            "file_type": "csv" | "excel" | "pdf" | "docx" | "text",
            "records": [ { field: value, ... }, ... ],
            "raw_text": "original text (for non-tabular files)",
            "field_mapping": { "original_col": "mapped_field", ... },
            "errors": [ "any parsing errors" ]
        }
    """
    if not os.path.exists(file_path):
        return {"status": "error", "errors": [f"File not found: {file_path}"], "records": []}

    ext = os.path.splitext(file_path)[1].lower()
    logger.info(f"Parsing file: {file_path} (type: {ext})")

    try:
        if ext == ".csv":
            return _parse_csv(file_path)
        elif ext in (".xlsx", ".xls"):
            return _parse_excel(file_path)
        elif ext == ".pdf":
            return _parse_pdf(file_path)
        elif ext == ".docx":
            return _parse_docx(file_path)
        elif ext in (".txt", ".md"):
            return _parse_text(file_path)
        else:
            return {"status": "error", "errors": [f"Unsupported file type: {ext}"], "records": []}

    except Exception as e:
        logger.error(f"File parsing failed: {e}", exc_info=True)
        return {"status": "error", "errors": [str(e)], "records": []}


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------
def _parse_csv(file_path: str) -> dict:
    """Parse CSV file with Thai or English column names."""
    df = pd.read_csv(file_path, encoding="utf-8-sig")
    return _dataframe_to_records(df, "csv")


# ---------------------------------------------------------------------------
# Excel parsing
# ---------------------------------------------------------------------------
def _parse_excel(file_path: str) -> dict:
    """Parse Excel file."""
    df = pd.read_excel(file_path)
    return _dataframe_to_records(df, "excel")


# ---------------------------------------------------------------------------
# DataFrame -> Records (shared by CSV / Excel)
# ---------------------------------------------------------------------------
COLUMN_MAP = {
    # Thai -> English field mapping
    "รหัสทัวร์": "tour_code",
    "รหัสโปรแกรม": "program_code",
    "รหัสกรุ๊ป": "tour_code",
    "โปรแกรมทัวร์": "program_code",
    "วันที่เดินทาง": "travel_date",
    "วันที่": "travel_date",
    "จำนวนลูกค้า หัก หนท.": "pax",
    "จำนวนลูกค้า": "pax",
    "จำนวนคน": "pax",
    "ยอดเบิก": "amount",
    "จำนวนเงิน": "amount",
    "ราคา": "amount",
    "คำอธิบาย": "description",
    "ประเภท": "charge_type",
    "สกุลเงิน": "currency",
    "เรท": "exchange_rate",
    "หมายเหตุ": "remark",
    # English aliases
    "tour_code": "tour_code",
    "group_code": "tour_code",
    "program_code": "program_code",
    "travel_date": "travel_date",
    "date": "travel_date",
    "pax": "pax",
    "size": "pax",
    "passengers": "pax",
    "amount": "amount",
    "price": "amount",
    "total": "amount",
    "description": "description",
    "type": "charge_type",
    "currency": "currency",
}


def _dataframe_to_records(df: pd.DataFrame, file_type: str) -> dict:
    """Convert a DataFrame to standardized expense records."""
    field_mapping = {}

    # Map columns
    for col in df.columns:
        col_stripped = str(col).strip()
        col_lower = col_stripped.lower()
        if col_stripped in COLUMN_MAP:
            mapped = COLUMN_MAP[col_stripped]
            df.rename(columns={col: mapped}, inplace=True)
            field_mapping[col_stripped] = mapped
        elif col_lower in COLUMN_MAP:
            mapped = COLUMN_MAP[col_lower]
            df.rename(columns={col: mapped}, inplace=True)
            field_mapping[col_stripped] = mapped

    # Clean data
    if "tour_code" in df.columns:
        df["tour_code"] = df["tour_code"].astype(str).str.strip()
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    if "pax" in df.columns:
        df["pax"] = pd.to_numeric(df["pax"], errors="coerce").fillna(0).astype(int)

    # Set defaults
    for col, default in [("currency", "THB"), ("charge_type", "other"), ("exchange_rate", 1.0)]:
        if col not in df.columns:
            df[col] = default

    # Validate and collect records
    records = []
    errors = []
    for idx, row in df.iterrows():
        record = row.to_dict()

        # Basic validation
        row_errors = []
        if not record.get("tour_code") or str(record.get("tour_code", "")).strip() in ("", "nan"):
            row_errors.append("Missing tour_code")
        if pd.isna(record.get("amount")) or record.get("amount", 0) <= 0:
            row_errors.append(f"Invalid amount: {record.get('amount')}")

        if row_errors:
            errors.append(f"Row {idx + 1}: {'; '.join(row_errors)}")
        else:
            # Clean NaN values
            clean_record = {}
            for k, v in record.items():
                if pd.isna(v):
                    clean_record[k] = None
                else:
                    clean_record[k] = v
            records.append(clean_record)

    return {
        "status": "success",
        "file_type": file_type,
        "columns_found": list(df.columns),
        "field_mapping": field_mapping,
        "total_rows": len(df),
        "valid_records": len(records),
        "invalid_records": len(errors),
        "records": records,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------
def _parse_pdf(file_path: str) -> dict:
    """Extract text from PDF and use LLM to identify expense fields."""
    try:
        import pdfplumber
    except ImportError:
        return {"status": "error", "errors": ["pdfplumber not installed"], "records": []}

    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

            # Also try extracting tables
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    text_parts.append(" | ".join(str(cell or "") for cell in row))

    raw_text = "\n".join(text_parts)
    if not raw_text.strip():
        return {"status": "error", "errors": ["No text extracted from PDF"], "records": [], "raw_text": ""}

    return _extract_records_with_llm(raw_text, "pdf")


# ---------------------------------------------------------------------------
# DOCX parsing
# ---------------------------------------------------------------------------
def _parse_docx(file_path: str) -> dict:
    """Extract text from DOCX and use LLM to identify expense fields."""
    try:
        from docx import Document
    except ImportError:
        return {"status": "error", "errors": ["python-docx not installed"], "records": []}

    doc = Document(file_path)
    text_parts = []

    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)

    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            text_parts.append(" | ".join(cells))

    raw_text = "\n".join(text_parts)
    if not raw_text.strip():
        return {"status": "error", "errors": ["No text extracted from DOCX"], "records": [], "raw_text": ""}

    return _extract_records_with_llm(raw_text, "docx")


# ---------------------------------------------------------------------------
# Plain text parsing
# ---------------------------------------------------------------------------
def _parse_text(file_path: str) -> dict:
    """Parse plain text file using LLM for field extraction."""
    with open(file_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    if not raw_text.strip():
        return {"status": "error", "errors": ["Empty file"], "records": [], "raw_text": ""}

    return _extract_records_with_llm(raw_text, "text")


# ---------------------------------------------------------------------------
# LLM-based extraction for unstructured documents
# ---------------------------------------------------------------------------
def _extract_records_with_llm(raw_text: str, file_type: str) -> dict:
    """Use OpenAI to extract structured expense records from raw text."""
    client = OpenAI(api_key=Config.OPENAI_API_KEY, timeout=90.0)

    prompt = f"""Extract expense/charge records from the following document text.

Also identify the **supplier name** (甲方 / Party A / the company issuing the bill).

## CURRENCY DETECTION (CRITICAL)
Detect the ACTUAL currency from the document. Do NOT default to THB.
Look for these clues:
- "RMB", "人民币", "元", "¥", "CNY" -> currency = "CNY"
- "THB", "บาท", "฿", "泰铢" -> currency = "THB"
- "USD", "$", "美元", "美金" -> currency = "USD"
- "EUR", "€", "欧元" -> currency = "EUR"
- "JPY", "円", "日元" -> currency = "JPY"
- "KRW", "₩", "韩元" -> currency = "KRW"
- If the amount summary shows "(RMB)" or "元" or mentions Chinese bank accounts only -> "CNY"
- If the supplier is a Chinese company with Chinese bank accounts -> likely "CNY"
- Only use "THB" if explicitly stated or if the document is clearly in Thai

## EXPENSE LINE ITEMS
Extract EACH expense line item as a SEPARATE record. Common items:
- 团费 / tour fare -> charge_type = "land_tour"
- 单房差 / single room supplement -> charge_type = "single_supplement"
- 服务费 / service fee -> charge_type = "service_fee"
- 导游费 / guide fee / 小费 / tips / 导服费 -> charge_type = "guide_tip"
- 机票 / 票价 / flight / airfare -> charge_type = "flight"
- 签证费 / visa fee -> charge_type = "visa"
- 酒店 / hotel / 住宿 / accommodation -> charge_type = "accommodation"
- 餐费 / meals -> charge_type = "meal"
- 车费 / transport / 包车 -> charge_type = "transport"
- 保险 / insurance -> charge_type = "insurance"
- 门票 / entrance / tickets -> charge_type = "entrance_fee"
- If unclear, use "other"

For EACH line item, extract:
- tour_code: Tour or group code (e.g., GO1TAO5NTAOQW260304). If multiple items share the same tour code, use the SAME code for each.
- program_code: Program code if available
- travel_date: Travel date or date range (e.g., "0304-0309")
- pax: Number of passengers / units for THIS line item
- unit_price: Price per person/unit (单价)
- amount: Total for this line (unit_price * pax). Calculate correctly from the document.
- currency: The detected currency code (see above)
- description: Original description text (Chinese or English as-is)
- charge_type: Category from the list above

Return ONLY valid JSON in this format:
{{
    "supplier_name": "the company/supplier name",
    "detected_currency": "CNY or THB or USD etc.",
    "currency_evidence": "brief explanation of how you detected the currency",
    "records": [
        {{
            "tour_code": "string",
            "program_code": "string or null",
            "travel_date": "string or null",
            "pax": number or null,
            "unit_price": number or null,
            "amount": number,
            "currency": "the detected currency",
            "description": "string",
            "charge_type": "string from categories above"
        }}
    ],
    "notes": "any observations about the data"
}}

Document text:
---
{raw_text[:6000]}
---"""

    try:
        response = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You extract structured data from documents. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=4000,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        records = result.get("records", [])
        supplier_name = result.get("supplier_name", "")
        detected_currency = result.get("detected_currency", "")
        currency_evidence = result.get("currency_evidence", "")

        if detected_currency:
            logger.info("Currency detected: %s (evidence: %s)", detected_currency, currency_evidence)

        for rec in records:
            rec["supplier_name"] = supplier_name
            if detected_currency and rec.get("currency") in ("THB", None, ""):
                rec["currency"] = detected_currency

        return {
            "status": "success",
            "file_type": file_type,
            "extraction_method": "llm",
            "supplier_name": supplier_name,
            "detected_currency": detected_currency,
            "currency_evidence": currency_evidence,
            "total_rows": len(records),
            "valid_records": len(records),
            "invalid_records": 0,
            "records": records,
            "raw_text": raw_text[:2000],
            "notes": result.get("notes", ""),
            "errors": [],
        }

    except Exception as e:
        logger.error(f"LLM extraction failed: {e}", exc_info=True)
        return {
            "status": "error",
            "file_type": file_type,
            "raw_text": raw_text[:2000],
            "errors": [f"AI extraction failed: {str(e)}"],
            "records": [],
        }

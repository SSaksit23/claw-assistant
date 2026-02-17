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


# Expected output fields for an expense record
EXPENSE_FIELDS = {
    "tour_code": "Tour/group code (e.g., BTMYSP16N240107)",
    "program_code": "Program code for the travel program",
    "travel_date": "Travel date or date range",
    "pax": "Number of passengers / group size",
    "amount": "Expense amount",
    "currency": "Currency (default THB)",
    "description": "Description of the expense",
    "charge_type": "Type: flight, visa, meal, taxi, accommodation, tour_guide, other",
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
    client = OpenAI(api_key=Config.OPENAI_API_KEY)

    prompt = f"""Extract expense/charge records from the following document text.

For each record, identify these fields:
- tour_code: Tour or group code (e.g., BTMYSP16N240107, JAPAN7N-001)
- program_code: Program code if available
- travel_date: Travel date or date range
- pax: Number of passengers / group size
- amount: Expense amount (number only)
- currency: Currency code (default THB if not specified)
- description: Brief description of the expense
- charge_type: One of: flight, visa, meal, taxi, accommodation, tour_guide, other

Return ONLY valid JSON in this format:
{{
    "records": [
        {{
            "tour_code": "string",
            "program_code": "string or null",
            "travel_date": "string or null",
            "pax": number or null,
            "amount": number,
            "currency": "THB",
            "description": "string",
            "charge_type": "other"
        }}
    ],
    "notes": "any observations about the data"
}}

Document text:
---
{raw_text[:4000]}
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
            max_tokens=2000,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        records = result.get("records", [])

        return {
            "status": "success",
            "file_type": file_type,
            "extraction_method": "llm",
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

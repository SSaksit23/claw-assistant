"""Data tools for loading, validating, and processing files (CSV, Excel, etc.)."""

import os
import logging
from typing import Optional

import pandas as pd

from config import Config

logger = logging.getLogger(__name__)


def load_csv(file_path: str) -> Optional[pd.DataFrame]:
    """
    Load and validate a CSV file for expense processing.

    Expected columns (Thai or English):
    - รหัสทัวร์ / tour_code
    - จำนวนลูกค้า หัก หนท. / pax
    - ยอดเบิก / amount

    Returns a DataFrame with standardized column names.
    """
    if not os.path.exists(file_path):
        logger.error(f"CSV file not found: {file_path}")
        return None

    try:
        df = pd.read_csv(file_path, encoding="utf-8-sig")
        logger.info(f"Loaded CSV: {len(df)} rows, columns: {list(df.columns)}")

        # Column name mapping (Thai -> English)
        column_map = {
            "รหัสทัวร์": "tour_code",
            "จำนวนลูกค้า หัก หนท.": "pax",
            "ยอดเบิก": "amount",
            "คำอธิบาย": "description",
            "ประเภท": "charge_type",
            "วันที่จ่าย": "payment_date",
            "สกุลเงิน": "currency",
            "เรท": "exchange_rate",
            "หมายเหตุ": "remark",
            "รหัสโปรแกรม": "program_code",
        }

        # Rename columns that match
        for thai_col, eng_col in column_map.items():
            if thai_col in df.columns:
                df.rename(columns={thai_col: eng_col}, inplace=True)

        # Validate required columns
        required = ["tour_code", "amount"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            logger.warning(f"Missing required columns: {missing}. Available: {list(df.columns)}")

        # Clean data
        if "tour_code" in df.columns:
            df["tour_code"] = df["tour_code"].astype(str).str.strip()
        if "amount" in df.columns:
            df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        if "pax" in df.columns:
            df["pax"] = pd.to_numeric(df["pax"], errors="coerce").fillna(0).astype(int)

        # Set defaults
        if "currency" not in df.columns:
            df["currency"] = "THB"
        if "exchange_rate" not in df.columns:
            df["exchange_rate"] = 1.0
        if "charge_type" not in df.columns:
            df["charge_type"] = "other"
        if "description" not in df.columns:
            df["description"] = df.get("tour_code", "Expense")

        return df

    except Exception as e:
        logger.error(f"Failed to load CSV: {e}", exc_info=True)
        return None


def load_excel(file_path: str) -> Optional[pd.DataFrame]:
    """Load an Excel file (.xlsx/.xls) and return a DataFrame."""
    if not os.path.exists(file_path):
        logger.error(f"Excel file not found: {file_path}")
        return None

    try:
        df = pd.read_excel(file_path)
        logger.info(f"Loaded Excel: {len(df)} rows, columns: {list(df.columns)}")
        return df
    except Exception as e:
        logger.error(f"Failed to load Excel: {e}", exc_info=True)
        return None


def validate_expense_data(df: pd.DataFrame) -> dict:
    """
    Validate expense data and return a summary.

    Returns dict with 'valid_count', 'invalid_count', 'errors', and 'records'.
    """
    errors = []
    valid_records = []

    for idx, row in df.iterrows():
        row_errors = []

        tour_code = row.get("tour_code", "")
        amount = row.get("amount")

        if not tour_code or pd.isna(tour_code) or str(tour_code).strip() == "":
            row_errors.append("Missing tour_code")

        if pd.isna(amount) or amount <= 0:
            row_errors.append(f"Invalid amount: {amount}")

        if row_errors:
            errors.append({"row": idx + 1, "errors": row_errors})
        else:
            valid_records.append(row.to_dict())

    return {
        "total_rows": len(df),
        "valid_count": len(valid_records),
        "invalid_count": len(errors),
        "errors": errors,
        "records": valid_records,
    }


def save_results(results: list, output_path: str = None) -> str:
    """Save processing results to a CSV file."""
    if not output_path:
        output_path = Config.OUTPUT_CSV

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    df = pd.DataFrame(results)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logger.info(f"Results saved to {output_path}")
    return output_path

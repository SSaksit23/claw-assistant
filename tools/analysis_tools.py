"""
Analysis tools for data aggregation, report generation, and visualization.

Used primarily by the Executive Agent to combine outputs from all other agents.
"""

import json
import os
import logging
from datetime import datetime
from typing import Optional

from config import Config

logger = logging.getLogger(__name__)


def aggregate_agent_data() -> dict:
    """
    Merge outputs from all agents into a unified dataset.

    Reads:
    - data/booking_data.json (from Data Analysis Agent)
    - data/market_analysis.json (from Market Analysis Agent)
    - data/expense_records.json (from Accounting Agent)

    Returns a combined dictionary with all available data.
    """
    aggregated = {
        "aggregated_at": datetime.now().isoformat(),
        "sources": {},
        "booking_data": None,
        "market_analysis": None,
        "expense_records": None,
        "summary_stats": {},
    }

    # Load booking data
    booking_path = os.path.join(Config.DATA_DIR, "booking_data.json")
    if os.path.exists(booking_path):
        try:
            with open(booking_path, "r", encoding="utf-8") as f:
                aggregated["booking_data"] = json.load(f)
            aggregated["sources"]["booking_data"] = {
                "path": booking_path,
                "loaded": True,
                "loaded_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning(f"Failed to load booking data: {e}")
            aggregated["sources"]["booking_data"] = {"loaded": False, "error": str(e)}

    # Load market analysis
    market_path = os.path.join(Config.DATA_DIR, "market_analysis.json")
    if os.path.exists(market_path):
        try:
            with open(market_path, "r", encoding="utf-8") as f:
                aggregated["market_analysis"] = json.load(f)
            aggregated["sources"]["market_analysis"] = {
                "path": market_path,
                "loaded": True,
                "loaded_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning(f"Failed to load market analysis: {e}")
            aggregated["sources"]["market_analysis"] = {"loaded": False, "error": str(e)}

    # Load expense records
    expense_path = os.path.join(Config.DATA_DIR, "expense_records.json")
    if os.path.exists(expense_path):
        try:
            with open(expense_path, "r", encoding="utf-8") as f:
                aggregated["expense_records"] = json.load(f)
            aggregated["sources"]["expense_records"] = {
                "path": expense_path,
                "loaded": True,
                "loaded_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning(f"Failed to load expense records: {e}")
            aggregated["sources"]["expense_records"] = {"loaded": False, "error": str(e)}

    # Compute summary stats
    stats = {}

    # Booking stats
    if aggregated["booking_data"]:
        bookings = aggregated["booking_data"].get("bookings", {})
        stats["total_bookings"] = bookings.get("count", 0)

    # Market stats
    if aggregated["market_analysis"]:
        raw = aggregated["market_analysis"].get("raw_data", {})
        stats["total_packages"] = raw.get("count", 0)

    # Expense stats
    if aggregated["expense_records"]:
        exp = aggregated["expense_records"]
        stats["total_expenses_processed"] = exp.get("total", 0)
        stats["expenses_succeeded"] = exp.get("success_count", 0)
        stats["expenses_failed"] = exp.get("fail_count", 0)

    aggregated["summary_stats"] = stats

    logger.info(f"Aggregated data from {len(aggregated['sources'])} sources")
    return aggregated


def generate_summary_stats(aggregated_data: dict) -> str:
    """Generate a plain-text summary of the aggregated data."""
    stats = aggregated_data.get("summary_stats", {})
    sources = aggregated_data.get("sources", {})

    lines = ["## Data Summary\n"]
    lines.append(f"**Aggregated at:** {aggregated_data.get('aggregated_at', 'N/A')}\n")

    # Sources status
    lines.append("### Data Sources")
    for name, info in sources.items():
        status = "Loaded" if info.get("loaded") else "Not available"
        lines.append(f"- **{name.replace('_', ' ').title()}**: {status}")

    lines.append("")

    # Stats
    if stats:
        lines.append("### Key Metrics")
        for key, value in stats.items():
            label = key.replace("_", " ").title()
            lines.append(f"- {label}: **{value}**")

    return "\n".join(lines)


def save_aggregated_data(data: dict, filename: str = "aggregated_data.json") -> str:
    """Save aggregated data to a JSON file."""
    output_path = os.path.join(Config.DATA_DIR, filename)
    os.makedirs(Config.DATA_DIR, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Aggregated data saved to {output_path}")
    return output_path

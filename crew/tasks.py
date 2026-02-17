"""
CrewAI task definitions for the multi-agent system.

Tasks are defined as templates that can be instantiated with specific
parameters when a crew is assembled for a particular job.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def create_login_task_description() -> str:
    """Task: Log into the QualityB2BPackage website."""
    return (
        "Log into the QualityB2BPackage website at https://www.qualityb2bpackage.com/ "
        "using the configured credentials. Verify that the login was successful by "
        "checking for the dashboard or a post-login page element. "
        "Report the login status."
    )


def create_data_extraction_task_description(data_type: str = "booking") -> str:
    """Task: Extract data from the website."""
    if data_type == "booking":
        return (
            "Navigate to the booking section at /booking and extract all available "
            "booking records. For each booking, capture: booking ID, customer name, "
            "package, travel date, status, total price, and payment status. "
            "Return the data as structured JSON."
        )
    elif data_type == "report":
        return (
            "Navigate to the seller report section at /report/report_seller and "
            "extract performance data. Capture report type, totals, and detailed "
            "breakdowns by country/province. Return as structured JSON."
        )
    elif data_type == "packages":
        return (
            "Navigate to /travelpackage and extract the product catalog. "
            "For each package, capture: ID, name, tour code, country, type, "
            "price, and duration. Return as structured JSON."
        )
    return f"Extract {data_type} data from the website."


def create_expense_task_description(
    tour_code: str,
    amount: float,
    currency: str = "THB",
    description: str = "",
) -> str:
    """Task: Record a single expense entry."""
    return (
        f"Record an expense entry on the QualityB2BPackage website:\n"
        f"- Tour Code: {tour_code}\n"
        f"- Amount: {amount} {currency}\n"
        f"- Description: {description or tour_code}\n\n"
        f"Steps:\n"
        f"1. Navigate to /charges_group/create\n"
        f"2. Select the program and tour code\n"
        f"3. Fill in the payment details and expense row\n"
        f"4. Submit the form\n"
        f"5. Extract and report the expense/order number"
    )


def create_market_analysis_task_description(destination: Optional[str] = None) -> str:
    """Task: Perform market analysis."""
    base = (
        "Analyze the company's travel package catalog from /travelpackage. "
        "Identify pricing patterns, popular destinations, and package types. "
    )
    if destination:
        base += f"Focus the analysis on packages for: {destination}. "
    base += (
        "Provide competitive insights including:\n"
        "- Price range analysis\n"
        "- Destination coverage\n"
        "- Package type distribution\n"
        "- Recommendations for pricing and product strategy"
    )
    return base


def create_executive_report_task_description() -> str:
    """Task: Generate executive report."""
    return (
        "Aggregate data from all other agents and generate a comprehensive "
        "executive report. Include:\n"
        "1. Executive summary (2-3 paragraphs)\n"
        "2. Financial summary (expenses, bookings, revenue)\n"
        "3. Market insights (top destinations, pricing position, trends)\n"
        "4. Operational metrics (success rates, records processed)\n"
        "5. Strategic recommendations (prioritized with expected impact)\n\n"
        "The report should be concise and actionable."
    )

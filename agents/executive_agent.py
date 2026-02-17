"""
Executive Agent -- Executive Intelligence Officer.

Aggregates data from all other agents and generates comprehensive
business intelligence reports with strategic recommendations.
"""

import json
import os
import logging
from datetime import datetime
from typing import Optional

from openai import OpenAI

from config import Config

logger = logging.getLogger(__name__)

client = OpenAI(api_key=Config.OPENAI_API_KEY)


def _load_agent_outputs() -> dict:
    """Load all available output files from other agents."""
    outputs = {}

    files_to_load = {
        "booking_data": os.path.join(Config.DATA_DIR, "booking_data.json"),
        "market_analysis": os.path.join(Config.DATA_DIR, "market_analysis.json"),
        "expense_records": os.path.join(Config.DATA_DIR, "expense_records.json"),
    }

    for key, path in files_to_load.items():
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    outputs[key] = json.load(f)
                logger.info(f"Loaded {key} from {path}")
            except Exception as e:
                logger.warning(f"Failed to load {key}: {e}")
                outputs[key] = None
        else:
            logger.info(f"{key} not available at {path}")
            outputs[key] = None

    return outputs


def _generate_report_with_llm(agent_outputs: dict) -> dict:
    """Use OpenAI to generate an executive report from aggregated data."""
    data_summary = {}

    # Summarize available data
    if agent_outputs.get("booking_data"):
        bd = agent_outputs["booking_data"]
        bookings = bd.get("bookings", {})
        data_summary["bookings"] = {
            "status": bookings.get("status", "unknown"),
            "count": bookings.get("count", 0),
            "sample": bookings.get("data", [])[:10],
        }
        report = bd.get("seller_report", {})
        data_summary["seller_report"] = {
            "status": report.get("status", "unknown"),
            "count": report.get("count", 0),
            "sample": report.get("data", [])[:10],
        }

    if agent_outputs.get("market_analysis"):
        ma = agent_outputs["market_analysis"]
        data_summary["market_analysis"] = ma.get("analysis", {})

    if agent_outputs.get("expense_records"):
        er = agent_outputs["expense_records"]
        data_summary["expenses"] = {
            "total": er.get("total", 0),
            "success_count": er.get("success_count", 0),
            "fail_count": er.get("fail_count", 0),
            "results_sample": er.get("results", [])[:10],
        }

    prompt = f"""Based on the following aggregated data from our multi-agent system, generate a comprehensive executive report.

Available data:
{json.dumps(data_summary, ensure_ascii=False, indent=2)}

Generate the report in JSON format:
{{
    "executive_summary": "2-3 paragraph overview of business performance and key findings",
    "financial_summary": {{
        "total_expenses": <number or null>,
        "total_bookings": <number or null>,
        "total_revenue_estimate": <number or null>,
        "currency": "THB",
        "expense_breakdown": [
            {{"category": "string", "amount": <number>, "percentage": <number>}}
        ]
    }},
    "market_insights": {{
        "top_destinations": ["list"],
        "pricing_position": "analysis",
        "market_trends": ["list of trends"]
    }},
    "operational_metrics": {{
        "submission_success_rate": <number or null>,
        "records_processed": <number or null>,
        "records_failed": <number or null>
    }},
    "recommendations": [
        {{
            "priority": "high/medium/low",
            "category": "category",
            "recommendation": "specific recommendation",
            "expected_impact": "expected impact"
        }}
    ],
    "data_completeness": {{
        "booking_data": <true/false>,
        "market_data": <true/false>,
        "expense_data": <true/false>,
        "missing_data_notes": ["any notes about missing data"]
    }}
}}

If data is missing for any section, note it clearly and provide reasonable estimates or recommendations based on available data."""

    try:
        response = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an Executive Intelligence Officer generating business reports "
                        "for a B2B travel package company. Be data-driven, concise, and actionable. "
                        "All monetary values should be in THB unless specified otherwise."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=3000,
            response_format={"type": "json_object"},
        )

        report = json.loads(response.choices[0].message.content)
        report["report_timestamp"] = datetime.now().isoformat()
        return report

    except Exception as e:
        logger.error(f"Executive report generation failed: {e}", exc_info=True)
        return {
            "executive_summary": f"Report generation encountered an error: {str(e)}",
            "recommendations": [
                {
                    "priority": "high",
                    "category": "system",
                    "recommendation": "Investigate report generation failure",
                    "expected_impact": "Restore reporting capability",
                }
            ],
            "report_timestamp": datetime.now().isoformat(),
        }


def _format_report_for_chat(report: dict) -> str:
    """Format the executive report as markdown for the chat interface."""
    md = "## Executive Report\n\n"

    # Executive summary
    if report.get("executive_summary"):
        md += f"{report['executive_summary']}\n\n"

    # Financial summary
    fin = report.get("financial_summary", {})
    if fin:
        md += "### Financial Summary\n"
        if fin.get("total_expenses") is not None:
            md += f"- Total Expenses: **{fin['total_expenses']:,.0f} {fin.get('currency', 'THB')}**\n"
        if fin.get("total_bookings") is not None:
            md += f"- Total Bookings: **{fin['total_bookings']}**\n"
        if fin.get("total_revenue_estimate") is not None:
            md += f"- Estimated Revenue: **{fin['total_revenue_estimate']:,.0f} {fin.get('currency', 'THB')}**\n"
        if fin.get("expense_breakdown"):
            md += "\n**Expense Breakdown:**\n"
            for item in fin["expense_breakdown"]:
                md += f"  - {item['category']}: {item.get('amount', 0):,.0f} ({item.get('percentage', 0):.1f}%)\n"
        md += "\n"

    # Market insights
    market = report.get("market_insights", {})
    if market:
        md += "### Market Insights\n"
        if market.get("top_destinations"):
            md += f"- Top Destinations: {', '.join(market['top_destinations'][:5])}\n"
        if market.get("pricing_position"):
            md += f"- Pricing Position: {market['pricing_position']}\n"
        if market.get("market_trends"):
            md += "- **Trends:**\n"
            for trend in market["market_trends"][:5]:
                md += f"  - {trend}\n"
        md += "\n"

    # Operational metrics
    ops = report.get("operational_metrics", {})
    if ops:
        md += "### Operational Metrics\n"
        if ops.get("records_processed") is not None:
            md += f"- Records Processed: {ops['records_processed']}\n"
        if ops.get("submission_success_rate") is not None:
            md += f"- Success Rate: {ops['submission_success_rate']}%\n"
        if ops.get("records_failed") is not None:
            md += f"- Records Failed: {ops['records_failed']}\n"
        md += "\n"

    # Recommendations
    recs = report.get("recommendations", [])
    if recs:
        md += "### Strategic Recommendations\n"
        for rec in recs:
            priority = rec.get("priority", "medium").upper()
            md += f"- **[{priority}]** {rec.get('recommendation', '')}\n"
            if rec.get("expected_impact"):
                md += f"  _Impact: {rec['expected_impact']}_\n"
        md += "\n"

    # Data completeness
    completeness = report.get("data_completeness", {})
    if completeness.get("missing_data_notes"):
        md += "### Data Notes\n"
        for note in completeness["missing_data_notes"]:
            md += f"- {note}\n"

    return md


def handle_executive_task(task_details: dict, emit_fn=None) -> dict:
    """
    Entry point called by the Assignment Agent.

    Aggregates available data and generates an executive report.
    """
    if emit_fn:
        emit_fn("agent_progress", {
            "agent": "Executive Agent",
            "message": "Loading data from other agents...",
        })

    # Load all available agent outputs
    agent_outputs = _load_agent_outputs()
    available_sources = [k for k, v in agent_outputs.items() if v is not None]

    if emit_fn:
        emit_fn("agent_progress", {
            "agent": "Executive Agent",
            "message": f"Data sources available: {', '.join(available_sources) or 'None'}. Generating report...",
        })

    # Generate report with LLM
    report = _generate_report_with_llm(agent_outputs)

    # Save report
    output_path = os.path.join(Config.DATA_DIR, "executive_report.json")
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Format for chat display
    chat_summary = _format_report_for_chat(report)
    chat_summary += f"\n\nFull report saved to `{output_path}`"

    return {"content": chat_summary, "data": report}

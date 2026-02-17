"""
CrewAI crew assembly and orchestration.

Assembles agents and tasks into crews for different workflow types:
- Expense processing crew
- Data analysis crew
- Full pipeline crew (all agents)
"""

import logging
from typing import Optional

from config import Config

logger = logging.getLogger(__name__)


def _get_llm_config() -> dict:
    """Return the LLM configuration for CrewAI agents."""
    return {
        "model": Config.OPENAI_MODEL,
        "api_key": Config.OPENAI_API_KEY,
        "temperature": 0.3,
    }


def create_expense_crew(records: list, emit_fn=None) -> dict:
    """
    Create and run an expense processing workflow.

    This uses the Accounting Agent directly (without full CrewAI overhead)
    since expense processing follows a deterministic workflow.
    """
    from agents.accounting_agent import handle_expense_task

    task_details = {
        "action": "process_expenses",
        "parameters": {"records": records},
    }

    return handle_expense_task(task_details, emit_fn=emit_fn)


def create_data_analysis_crew(analysis_type: str = "booking", emit_fn=None) -> dict:
    """
    Create and run a data analysis workflow.
    """
    from agents.data_analysis_agent import handle_data_analysis_task

    task_details = {
        "action": f"analyze_{analysis_type}",
        "parameters": {"analysis_type": analysis_type},
    }

    return handle_data_analysis_task(task_details, emit_fn=emit_fn)


def create_market_analysis_crew(destination: Optional[str] = None, emit_fn=None) -> dict:
    """
    Create and run a market analysis workflow.
    """
    from agents.market_analysis_agent import handle_market_analysis_task

    task_details = {
        "action": "market_analysis",
        "parameters": {"destination": destination},
    }

    return handle_market_analysis_task(task_details, emit_fn=emit_fn)


def create_executive_report_crew(emit_fn=None) -> dict:
    """
    Create and run the full pipeline: data -> market -> executive report.
    """
    from agents.executive_agent import handle_executive_task

    task_details = {
        "action": "generate_executive_report",
        "parameters": {},
    }

    return handle_executive_task(task_details, emit_fn=emit_fn)


def create_full_pipeline_crew(file_path: str = None, emit_fn=None) -> dict:
    """
    Run the complete multi-agent pipeline:
    1. Data Analysis Agent -> extract booking & report data
    2. Market Analysis Agent -> analyze packages
    3. Accounting Agent -> process expenses (if file provided)
    4. Executive Agent -> aggregate and report

    Returns a combined result.
    """
    results = {}

    # Step 1: Data Analysis
    if emit_fn:
        emit_fn("agent_status", {
            "agent": "Data Analysis Agent",
            "status": "working",
            "message": "Extracting data...",
        })

    try:
        data_result = create_data_analysis_crew("all", emit_fn)
        results["data_analysis"] = data_result
    except Exception as e:
        logger.error(f"Data analysis failed: {e}")
        results["data_analysis"] = {"content": f"Failed: {e}", "data": None}

    if emit_fn:
        emit_fn("agent_status", {
            "agent": "Data Analysis Agent",
            "status": "done",
            "message": "Complete",
        })

    # Step 2: Market Analysis
    if emit_fn:
        emit_fn("agent_status", {
            "agent": "Market Analysis Agent",
            "status": "working",
            "message": "Analyzing market...",
        })

    try:
        market_result = create_market_analysis_crew(emit_fn=emit_fn)
        results["market_analysis"] = market_result
    except Exception as e:
        logger.error(f"Market analysis failed: {e}")
        results["market_analysis"] = {"content": f"Failed: {e}", "data": None}

    if emit_fn:
        emit_fn("agent_status", {
            "agent": "Market Analysis Agent",
            "status": "done",
            "message": "Complete",
        })

    # Step 3: Expense processing (if file provided)
    if file_path:
        if emit_fn:
            emit_fn("agent_status", {
                "agent": "Accounting Agent",
                "status": "working",
                "message": "Processing expenses...",
            })

        try:
            from agents.accounting_agent import handle_expense_task
            expense_result = handle_expense_task({}, file_path, emit_fn)
            results["accounting"] = expense_result
        except Exception as e:
            logger.error(f"Expense processing failed: {e}")
            results["accounting"] = {"content": f"Failed: {e}", "data": None}

        if emit_fn:
            emit_fn("agent_status", {
                "agent": "Accounting Agent",
                "status": "done",
                "message": "Complete",
            })

    # Step 4: Executive Report
    if emit_fn:
        emit_fn("agent_status", {
            "agent": "Executive Agent",
            "status": "working",
            "message": "Generating report...",
        })

    try:
        exec_result = create_executive_report_crew(emit_fn)
        results["executive"] = exec_result
    except Exception as e:
        logger.error(f"Executive report failed: {e}")
        results["executive"] = {"content": f"Failed: {e}", "data": None}

    if emit_fn:
        emit_fn("agent_status", {
            "agent": "Executive Agent",
            "status": "done",
            "message": "Complete",
        })

    # Combine results
    combined_content = "## Full Pipeline Results\n\n"
    for key, val in results.items():
        combined_content += f"### {key.replace('_', ' ').title()}\n"
        combined_content += val.get("content", "No output") + "\n\n"

    return {"content": combined_content, "data": results}

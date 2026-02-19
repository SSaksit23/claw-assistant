"""
Market Analysis Agent -- Market Intelligence Specialist.

Analyzes travel packages, competitive landscape, and market trends
from the QualityB2BPackage website product catalog.
"""

import json
import os
import logging
from datetime import datetime
from typing import Optional

from openai import OpenAI

from tools.browser_manager import BrowserManager, run_async
from tools import browser_tools
from config import Config

logger = logging.getLogger(__name__)

client = OpenAI(api_key=Config.OPENAI_API_KEY)


async def _scrape_travel_packages(destination: Optional[str] = None, emit_fn=None,
                                   session_id: str = "default") -> dict:
    """Scrape travel package catalog from /travelpackage."""
    manager = BrowserManager.get_instance(session_id)
    page = await manager.get_page()

    try:
        if emit_fn:
            emit_fn("agent_progress", {
                "agent": "Market Analysis Agent",
                "message": "Navigating to travel packages page...",
            })

        url = Config.TRAVEL_PACKAGE_URL
        if destination:
            url += f"?keyword={destination}"

        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(2000)
        await manager.screenshot("travel_packages")

        # Extract table data
        packages = await browser_tools.scrape_table_data(page)

        logger.info(f"Extracted {len(packages)} travel packages")
        return {
            "status": "success",
            "count": len(packages),
            "data": packages,
            "filter": destination,
            "scraped_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Travel package extraction failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e), "data": []}


def _analyze_packages_with_llm(packages: list, destination: Optional[str] = None) -> dict:
    """Use OpenAI to analyze the scraped package data."""
    if not packages:
        return {
            "analysis": "No package data available for analysis.",
            "recommendations": [],
        }

    prompt = f"""Analyze the following travel package data from Quality B2B Package:

{json.dumps(packages[:50], ensure_ascii=False, indent=2)}

Total packages in catalog: {len(packages)}
{"Focus on destination: " + destination if destination else ""}

Provide a comprehensive market analysis in JSON format:
{{
    "summary": "2-3 paragraph market overview",
    "total_packages": <number>,
    "destinations": {{
        "top_destinations": ["list of most popular destinations"],
        "coverage_analysis": "analysis of destination coverage"
    }},
    "pricing": {{
        "analysis": "pricing strategy analysis",
        "recommendations": ["pricing recommendations"]
    }},
    "product_mix": {{
        "types": ["list of package types found"],
        "analysis": "product mix analysis"
    }},
    "trends": ["list of observed market trends"],
    "recommendations": [
        {{
            "priority": "high/medium/low",
            "category": "category",
            "recommendation": "specific actionable recommendation",
            "expected_impact": "expected business impact"
        }}
    ]
}}"""

    try:
        response = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a market analysis specialist for the travel industry. Provide data-driven insights and actionable recommendations.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )

        analysis = json.loads(response.choices[0].message.content)
        return analysis

    except Exception as e:
        logger.error(f"LLM analysis failed: {e}", exc_info=True)
        return {
            "summary": f"Analysis could not be completed: {str(e)}",
            "recommendations": [],
        }


async def _run_market_analysis(destination: Optional[str] = None, emit_fn=None,
                               session_id: str = "default",
                               website_username: str = None,
                               website_password: str = None) -> dict:
    """Run the complete market analysis workflow."""
    from tools.browser_manager import BrowserManager
    BrowserManager.acquire(session_id)
    try:
        return await _run_market_analysis_inner(
            destination, emit_fn, session_id, website_username, website_password)
    finally:
        BrowserManager.release(session_id)


async def _run_market_analysis_inner(destination, emit_fn, session_id,
                                     website_username, website_password):
    if emit_fn:
        emit_fn("agent_progress", {
            "agent": "Market Analysis Agent",
            "message": "Logging in...",
        })

    login_result = await browser_tools.login(
        username=website_username, password=website_password, session_id=session_id,
    )
    if login_result["status"] != "success":
        return {
            "content": f"Login failed: {login_result['message']}",
            "data": None,
        }

    packages_result = await _scrape_travel_packages(destination, emit_fn, session_id=session_id)

    if packages_result["status"] != "success" or not packages_result["data"]:
        return {
            "content": f"Failed to extract package data: {packages_result.get('error', 'No data found')}",
            "data": packages_result,
        }

    # Analyze with LLM
    if emit_fn:
        emit_fn("agent_progress", {
            "agent": "Market Analysis Agent",
            "message": "Analyzing market data with AI...",
        })

    analysis = _analyze_packages_with_llm(packages_result["data"], destination)

    # Combine results
    full_result = {
        "raw_data": packages_result,
        "analysis": analysis,
        "generated_at": datetime.now().isoformat(),
    }

    # Save to file
    output_path = os.path.join(Config.DATA_DIR, "market_analysis.json")
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(full_result, f, ensure_ascii=False, indent=2)

    # Build summary for chat
    summary = "## Market Analysis Report\n\n"
    summary += analysis.get("summary", "Analysis complete.") + "\n\n"

    if analysis.get("destinations", {}).get("top_destinations"):
        summary += "### Top Destinations\n"
        for dest in analysis["destinations"]["top_destinations"][:5]:
            summary += f"- {dest}\n"
        summary += "\n"

    if analysis.get("pricing", {}).get("analysis"):
        summary += f"### Pricing Analysis\n{analysis['pricing']['analysis']}\n\n"

    if analysis.get("trends"):
        summary += "### Market Trends\n"
        for trend in analysis["trends"][:5]:
            summary += f"- {trend}\n"
        summary += "\n"

    if analysis.get("recommendations"):
        summary += "### Recommendations\n"
        for rec in analysis["recommendations"][:5]:
            priority = rec.get("priority", "medium").upper()
            summary += f"- **[{priority}]** {rec.get('recommendation', '')}\n"
        summary += "\n"

    summary += f"\nFull report saved to `{output_path}`"

    return {"content": summary, "data": full_result}


def handle_market_analysis_task(task_details: dict, emit_fn=None,
                                session_id: str = "default",
                                website_username: str = None,
                                website_password: str = None) -> dict:
    """Entry point called by the Assignment Agent."""
    params = task_details.get("parameters", {})
    destination = params.get("destination")

    result = run_async(_run_market_analysis(
        destination, emit_fn,
        session_id=session_id,
        website_username=website_username,
        website_password=website_password,
    ))
    return result

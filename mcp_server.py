"""
MCP Server -- Model Context Protocol integration.

Exposes the multi-agent system's capabilities as MCP tools
for integration with external AI assistants (Claude Desktop, etc.).

Usage:
    python mcp_server.py

Configure in your MCP client (e.g., claude_desktop_config.json):
    {
        "mcpServers": {
            "web365-clawbot": {
                "command": "python",
                "args": ["path/to/mcp_server.py"]
            }
        }
    }
"""

import json
import logging
import os
import sys
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _get_mcp_server():
    """Create and configure the MCP server with all tools."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import Tool, TextContent
    except ImportError:
        logger.error(
            "MCP library not installed. Install with: pip install mcp\n"
            "Falling back to standalone JSON-RPC mode."
        )
        return None, None

    server = Server("web365-clawbot")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List all available MCP tools."""
        return [
            Tool(
                name="process_single_expense",
                description=(
                    "Process a single expense entry on qualityb2bpackage.com. "
                    "Automates login, form navigation, filling, and submission."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tour_code": {
                            "type": "string",
                            "description": "Tour code (e.g., BTMYSP16N240107)",
                        },
                        "amount": {
                            "type": "number",
                            "description": "Expense amount",
                        },
                        "pax": {
                            "type": "integer",
                            "description": "Number of passengers",
                            "default": 0,
                        },
                        "currency": {
                            "type": "string",
                            "description": "Currency code",
                            "default": "THB",
                        },
                        "description": {
                            "type": "string",
                            "description": "Expense description",
                            "default": "",
                        },
                        "program_code": {
                            "type": "string",
                            "description": "Program code (optional, auto-detected if omitted)",
                            "default": "",
                        },
                    },
                    "required": ["tour_code", "amount"],
                },
            ),
            Tool(
                name="run_expense_automation",
                description=(
                    "Process multiple expense entries in batch from a list. "
                    "Each entry needs tour_code and amount at minimum."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entries": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "tour_code": {"type": "string"},
                                    "amount": {"type": "number"},
                                    "pax": {"type": "integer", "default": 0},
                                    "currency": {"type": "string", "default": "THB"},
                                },
                                "required": ["tour_code", "amount"],
                            },
                            "description": "Array of expense entries",
                        },
                    },
                    "required": ["entries"],
                },
            ),
            Tool(
                name="extract_packages",
                description="Extract travel packages from the qualityb2bpackage.com catalog.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "destination": {
                            "type": "string",
                            "description": "Filter by destination/keyword (optional)",
                            "default": "",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max packages to extract",
                            "default": 50,
                        },
                    },
                },
            ),
            Tool(
                name="analyze_bookings",
                description="Extract and analyze booking data from the website.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "analysis_type": {
                            "type": "string",
                            "enum": ["booking", "report", "all"],
                            "default": "all",
                            "description": "Type of analysis to run",
                        },
                    },
                },
            ),
            Tool(
                name="generate_executive_report",
                description=(
                    "Generate an executive summary report aggregating all available "
                    "data from bookings, market analysis, and expenses."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="market_analysis",
                description=(
                    "Analyze travel packages and competitive landscape. "
                    "Provides insights on pricing, destinations, and market trends."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "destination": {
                            "type": "string",
                            "description": "Focus analysis on specific destination (optional)",
                            "default": "",
                        },
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle MCP tool calls."""
        logger.info(f"MCP tool called: {name} with args: {arguments}")

        try:
            result = await _execute_tool(name, arguments)
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        except Exception as e:
            logger.error(f"MCP tool {name} failed: {e}", exc_info=True)
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    return server, stdio_server


async def _execute_tool(name: str, arguments: dict) -> dict:
    """Execute the requested MCP tool."""
    if name == "process_single_expense":
        from agents.accounting_agent import handle_expense_task

        task_details = {
            "action": "process_single",
            "parameters": {
                "tour_code": arguments["tour_code"],
                "amount": arguments["amount"],
                "pax": arguments.get("pax", 0),
                "currency": arguments.get("currency", "THB"),
                "description": arguments.get("description", ""),
                "program_code": arguments.get("program_code", ""),
            },
        }
        return handle_expense_task(task_details)

    elif name == "run_expense_automation":
        from agents.accounting_agent import handle_expense_task
        from tools.data_tools import validate_expense_data
        import pandas as pd

        entries = arguments["entries"]
        df = pd.DataFrame(entries)
        validation = validate_expense_data(df)

        task_details = {
            "action": "process_batch",
            "parameters": {"records": validation["records"]},
        }
        return handle_expense_task(task_details)

    elif name == "extract_packages":
        from agents.market_analysis_agent import handle_market_analysis_task

        task_details = {
            "action": "extract_packages",
            "parameters": {
                "destination": arguments.get("destination", ""),
            },
        }
        return handle_market_analysis_task(task_details)

    elif name == "analyze_bookings":
        from agents.data_analysis_agent import handle_data_analysis_task

        task_details = {
            "action": "analyze",
            "parameters": {
                "analysis_type": arguments.get("analysis_type", "all"),
            },
        }
        return handle_data_analysis_task(task_details)

    elif name == "generate_executive_report":
        from agents.executive_agent import handle_executive_task

        task_details = {
            "action": "generate_executive_report",
            "parameters": {},
        }
        return handle_executive_task(task_details)

    elif name == "market_analysis":
        from agents.market_analysis_agent import handle_market_analysis_task

        task_details = {
            "action": "market_analysis",
            "parameters": {
                "destination": arguments.get("destination", ""),
            },
        }
        return handle_market_analysis_task(task_details)

    else:
        return {"error": f"Unknown tool: {name}"}


async def main():
    """Run the MCP server."""
    server, stdio_server_fn = _get_mcp_server()

    if server is None:
        # Fallback: print available tools as JSON
        print(json.dumps({
            "name": "web365-clawbot",
            "version": "1.0.0",
            "tools": [
                "process_single_expense",
                "run_expense_automation",
                "extract_packages",
                "analyze_bookings",
                "generate_executive_report",
                "market_analysis",
            ],
            "status": "MCP library not installed, install with: pip install mcp",
        }, indent=2))
        return

    logger.info("Starting Web365 ClawBot MCP Server...")
    async with stdio_server_fn() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

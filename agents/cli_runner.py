"""
Standalone CLI runner for ClawBot agents.

Allows each agent to be invoked as a process from the command line,
enabling orchestration by klaw or any external scheduler.

Usage:
    python -m agents.cli_runner --agent accounting --task '{"action":"process","parameters":{"tour_code":"BTMYSP16N240107","amount":1000}}'
    python -m agents.cli_runner --agent data_analysis --task '{"action":"scrape","parameters":{"analysis_type":"all"}}'
    python -m agents.cli_runner --agent market_analysis --task '{"action":"analyze","parameters":{"destination":"Japan"}}'
    python -m agents.cli_runner --agent executive --task '{"action":"generate_report"}'
    python -m agents.cli_runner --agent admin --task '{"action":"list_expenses"}'
"""

import argparse
import json
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("cli_runner")

AGENT_REGISTRY = {
    "accounting": {
        "module": "agents.accounting_agent",
        "handler": "handle_expense_task",
        "description": "Process expense records on qualityb2bpackage.com",
    },
    "data_analysis": {
        "module": "agents.data_analysis_agent",
        "handler": "handle_data_analysis_task",
        "description": "Extract booking data and seller reports",
    },
    "market_analysis": {
        "module": "agents.market_analysis_agent",
        "handler": "handle_market_analysis_task",
        "description": "Analyze travel packages and market trends",
    },
    "executive": {
        "module": "agents.executive_agent",
        "handler": "handle_executive_task",
        "description": "Generate executive intelligence reports",
    },
    "admin": {
        "module": "agents.admin_agent",
        "handler": "handle_admin_task",
        "description": "Administrative record management and lookups",
    },
}


def cli_emit(event: str, data: dict):
    """Emit progress events to stderr so stdout stays clean for result JSON."""
    if event == "agent_progress":
        agent = data.get("agent", "Agent")
        message = data.get("message", "")
        print(f"[{agent}] {message}", file=sys.stderr)
    elif event == "agent_status":
        agent = data.get("agent", "Agent")
        status = data.get("status", "")
        print(f"[{agent}] status={status}", file=sys.stderr)


def run_agent(agent_name: str, task_json: str, file_path: str = None) -> dict:
    """Invoke an agent by name and return its result."""
    if agent_name not in AGENT_REGISTRY:
        return {
            "status": "error",
            "error": f"Unknown agent: {agent_name}",
            "available_agents": list(AGENT_REGISTRY.keys()),
        }

    entry = AGENT_REGISTRY[agent_name]

    try:
        task_details = json.loads(task_json) if task_json else {}
    except json.JSONDecodeError as e:
        return {"status": "error", "error": f"Invalid task JSON: {e}"}

    logger.info("Invoking agent=%s task=%s file=%s", agent_name, task_details, file_path)

    try:
        import importlib
        mod = importlib.import_module(entry["module"])
        handler = getattr(mod, entry["handler"])

        if agent_name == "accounting":
            result = handler(task_details, file_path=file_path, emit_fn=cli_emit)
        elif agent_name in ("data_analysis", "market_analysis", "executive"):
            result = handler(task_details, emit_fn=cli_emit)
        elif agent_name == "admin":
            result = handler(task_details, emit_fn=cli_emit)
        else:
            result = handler(task_details, emit_fn=cli_emit)

        return {"status": "success", "agent": agent_name, "result": result}

    except Exception as e:
        logger.error("Agent %s failed: %s", agent_name, e, exc_info=True)
        return {"status": "error", "agent": agent_name, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="ClawBot Agent CLI Runner — invoke agents from the command line",
    )
    parser.add_argument(
        "--agent", "-a",
        choices=list(AGENT_REGISTRY.keys()),
        help="Agent to invoke",
    )
    parser.add_argument(
        "--task", "-t",
        default="{}",
        help="Task details as JSON string",
    )
    parser.add_argument(
        "--file", "-f",
        default=None,
        help="Path to input file (for accounting agent)",
    )
    parser.add_argument(
        "--list-agents",
        action="store_true",
        help="List all available agents and exit",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Write result JSON to file instead of stdout",
    )

    args = parser.parse_args()

    if args.list_agents:
        for name, info in AGENT_REGISTRY.items():
            print(f"  {name:20s} {info['description']}")
        sys.exit(0)

    if not args.agent:
        parser.error("--agent is required (or use --list-agents)")

    result = run_agent(args.agent, args.task, args.file)

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        logger.info("Result written to %s", args.output)
    else:
        print(output_json)

    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()

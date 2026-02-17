"""
n8n Workflow Integration Service.

Triggers n8n workflows via webhook and receives callbacks.
If n8n is not configured, falls back to direct execution.

n8n Webhook Setup:
1. Create a Webhook node in n8n (trigger)
2. Set the webhook URL in N8N_EXPENSE_WORKFLOW_URL
3. n8n workflow processes the data and calls back to Flask API
"""

import logging
import requests
from typing import Optional

from config import Config

logger = logging.getLogger(__name__)


def is_n8n_enabled() -> bool:
    """Check if n8n integration is configured and enabled."""
    return Config.N8N_ENABLED and bool(Config.N8N_EXPENSE_WORKFLOW_URL)


def trigger_expense_workflow(
    records: list,
    callback_url: str,
    job_id: str,
) -> dict:
    """
    Trigger the n8n expense processing workflow via webhook.

    The n8n workflow should:
    1. Receive the parsed expense records
    2. For each record: call POST /api/expenses on this server
    3. Collect results
    4. Call POST /api/callback with the final results

    Args:
        records: List of parsed expense records
        callback_url: URL for n8n to POST results back to
        job_id: Unique job identifier for tracking

    Returns:
        {"status": "triggered", "job_id": "..."} on success
    """
    webhook_url = Config.N8N_EXPENSE_WORKFLOW_URL

    if not webhook_url:
        return {
            "status": "error",
            "message": "N8N_EXPENSE_WORKFLOW_URL not configured",
        }

    payload = {
        "job_id": job_id,
        "callback_url": callback_url,
        "callback_secret": Config.N8N_CALLBACK_SECRET,
        "records": records,
        "config": {
            "api_base_url": f"http://localhost:{Config.FLASK_PORT}/api",
        },
    }

    try:
        logger.info(f"Triggering n8n workflow: {webhook_url} (job={job_id}, records={len(records)})")
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()

        return {
            "status": "triggered",
            "job_id": job_id,
            "n8n_response": response.json() if response.text else {},
        }

    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to n8n. Is it running?")
        return {
            "status": "error",
            "message": "Cannot connect to n8n server. Make sure n8n is running.",
        }
    except Exception as e:
        logger.error(f"Failed to trigger n8n workflow: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


def trigger_custom_workflow(
    webhook_url: str,
    data: dict,
) -> dict:
    """Trigger any n8n workflow by webhook URL."""
    try:
        response = requests.post(webhook_url, json=data, timeout=30)
        response.raise_for_status()
        return {"status": "success", "response": response.json() if response.text else {}}
    except Exception as e:
        logger.error(f"n8n webhook failed: {e}")
        return {"status": "error", "message": str(e)}

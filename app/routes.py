"""
HTTP routes for the web application.

Serves:
1. Chat UI page (GET /)
2. File upload (POST /upload)
3. REST API endpoints for n8n integration (/api/*)
"""

import os
import uuid
import json
import logging
from datetime import datetime

from flask import Blueprint, render_template, request, jsonify
from werkzeug.utils import secure_filename

from config import Config

logger = logging.getLogger(__name__)

main_bp = Blueprint("main", __name__)

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls", "pdf", "docx", "txt"}


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ===================================================================
# Page routes
# ===================================================================
@main_bp.route("/")
def index():
    """Serve the main chat interface."""
    return render_template("chat.html")


# ===================================================================
# File upload
# ===================================================================
@main_bp.route("/upload", methods=["POST"])
def upload_file():
    """Handle file uploads (CSV, Excel, PDF, DOCX)."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not _allowed_file(file.filename):
        return jsonify({
            "error": f"File type not allowed. Accepted: {', '.join(ALLOWED_EXTENSIONS)}"
        }), 400

    os.makedirs(Config.UPLOAD_DIR, exist_ok=True)
    filename = secure_filename(file.filename)
    unique_name = f"{uuid.uuid4().hex[:8]}_{filename}"
    filepath = os.path.join(Config.UPLOAD_DIR, unique_name)
    file.save(filepath)

    logger.info(f"File uploaded: {unique_name} -> {filepath}")
    return jsonify({
        "status": "uploaded",
        "filename": unique_name,
        "original_name": file.filename,
        "path": filepath,
    })


# ===================================================================
# Health check
# ===================================================================
@main_bp.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "service": "web365-clawbot",
        "n8n_enabled": Config.N8N_ENABLED,
        "timestamp": datetime.now().isoformat(),
    })


# ===================================================================
# REST API for n8n integration
# ===================================================================

@main_bp.route("/api/login", methods=["POST"])
def api_login():
    """Login to qualityb2bpackage.com. Called by n8n."""
    from tools.browser_manager import run_async
    from tools.browser_tools import login

    result = run_async(login())
    return jsonify(result)


@main_bp.route("/api/expenses", methods=["POST"])
def api_create_expense():
    """
    Create a single expense record. Called by n8n for each record.

    Body: { "tour_code": "...", "amount": 1000, "pax": 10, ... }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    if not data.get("tour_code") or not data.get("amount"):
        return jsonify({"error": "tour_code and amount are required"}), 400

    from services.expense_service import process_single_expense_api
    result = process_single_expense_api(data)
    return jsonify(result)


@main_bp.route("/api/batch-expenses", methods=["POST"])
def api_batch_expenses():
    """
    Process multiple expenses in batch. Called by n8n.

    Body: { "expenses": [ {tour_code, amount, ...}, ... ] }
    """
    data = request.get_json()
    if not data or not data.get("expenses"):
        return jsonify({"error": "expenses array is required"}), 400

    from services.expense_service import process_single_expense_api
    from tools.browser_manager import run_async
    from tools.browser_tools import login, close_browser

    # Login once
    login_result = run_async(login())
    if login_result["status"] != "success":
        return jsonify({"error": f"Login failed: {login_result['message']}"}), 500

    results = []
    for entry in data["expenses"]:
        result = process_single_expense_api(entry)
        results.append(result)

    # Close browser
    run_async(close_browser())

    success = sum(1 for r in results if r.get("status") == "success")
    failed = len(results) - success

    return jsonify({
        "total": len(results),
        "success": success,
        "failed": failed,
        "results": results,
    })


@main_bp.route("/api/parse", methods=["POST"])
def api_parse_file():
    """
    Parse an uploaded file and return extracted records.
    Does NOT submit anything -- just parses.

    Body: { "file_path": "data/uploads/xxx.csv" }
    Or upload a file directly.
    """
    if "file" in request.files:
        file = request.files["file"]
        os.makedirs(Config.UPLOAD_DIR, exist_ok=True)
        filename = secure_filename(file.filename)
        filepath = os.path.join(Config.UPLOAD_DIR, filename)
        file.save(filepath)
    else:
        data = request.get_json() or {}
        filepath = data.get("file_path", "")

    if not filepath or not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 400

    from services.document_parser import parse_file
    result = parse_file(filepath)
    return jsonify(result)


@main_bp.route("/api/packages", methods=["GET"])
def api_list_packages():
    """Extract travel packages from the website."""
    from tools.browser_manager import run_async
    from tools.browser_tools import login, scrape_table_data, close_browser

    keyword = request.args.get("keyword", "")
    limit = int(request.args.get("limit", 50))

    async def _get_packages():
        await login()
        from tools.browser_manager import BrowserManager
        manager = BrowserManager.get_instance()
        page = await manager.get_page()

        url = Config.TRAVEL_PACKAGE_URL
        if keyword:
            url += f"?keyword={keyword}"
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(2000)

        data = await scrape_table_data(page)
        await close_browser()
        return data[:limit]

    packages = run_async(_get_packages())
    return jsonify({"count": len(packages), "packages": packages})


# ===================================================================
# Itinerary Analysis API  (adapted from itin-analyzer prototype)
# ===================================================================

@main_bp.route("/api/itinerary/analyze", methods=["POST"])
def api_analyze_itinerary():
    """
    Analyse a single itinerary file (PDF, DOCX, TXT).

    Upload a file OR provide {"file_path": "..."} in the body.
    Returns structured itinerary data: tour name, duration,
    destinations, pricing, flights, inclusions/exclusions,
    daily breakdown.
    """
    from tools.itinerary_tools import analyze_itinerary_tool

    # Resolve file
    filepath = _resolve_itinerary_file(request)
    if isinstance(filepath, tuple):
        return filepath  # error response

    language = (request.form.get("language") or
                (request.get_json(silent=True) or {}).get("language", "auto"))

    result = analyze_itinerary_tool(filepath, language=language, save_output=True)
    status_code = 200 if result.get("status") == "success" else 422
    return jsonify(result), status_code


@main_bp.route("/api/itinerary/compare", methods=["POST"])
def api_compare_itineraries():
    """
    Compare multiple itinerary files side by side.

    Upload multiple files via form-data (key: files)
    or provide {"file_paths": ["...", "..."]} in the body.

    Returns a markdown comparison report.
    """
    from tools.itinerary_tools import compare_itineraries_tool

    file_paths = []
    language = "English"

    if request.content_type and "multipart/form-data" in request.content_type:
        files = request.files.getlist("files")
        language = request.form.get("language", "English")
        for f in files:
            os.makedirs(Config.ITINERARY_UPLOAD_DIR, exist_ok=True)
            fname = secure_filename(f.filename)
            fpath = os.path.join(Config.ITINERARY_UPLOAD_DIR, f"{uuid.uuid4().hex[:8]}_{fname}")
            f.save(fpath)
            file_paths.append(fpath)
    else:
        data = request.get_json(silent=True) or {}
        file_paths = data.get("file_paths", [])
        language = data.get("language", "English")

    if len(file_paths) < 2:
        return jsonify({"error": "Provide at least 2 itinerary files"}), 400

    result = compare_itineraries_tool(
        itinerary_files=file_paths, language=language, save_output=True
    )
    status_code = 200 if result.get("status") == "success" else 422
    return jsonify(result), status_code


@main_bp.route("/api/itinerary/market-intelligence", methods=["POST"])
def api_market_intelligence():
    """
    Run the full market intelligence pipeline.

    Upload multiple files or provide:
    {
        "file_paths": ["...", "..."],
        "include_web_research": true,
        "fast_mode": true
    }

    Pipeline: Extract -> Analyse Themes -> Web Research -> Aggregate -> Report
    """
    from tools.itinerary_tools import market_intelligence_tool

    file_paths = []
    document_texts = []
    include_web = True
    fast_mode = True

    if request.content_type and "multipart/form-data" in request.content_type:
        files = request.files.getlist("files")
        include_web = request.form.get("include_web_research", "true").lower() == "true"
        fast_mode = request.form.get("fast_mode", "true").lower() == "true"
        for f in files:
            os.makedirs(Config.ITINERARY_UPLOAD_DIR, exist_ok=True)
            fname = secure_filename(f.filename)
            fpath = os.path.join(Config.ITINERARY_UPLOAD_DIR, f"{uuid.uuid4().hex[:8]}_{fname}")
            f.save(fpath)
            file_paths.append(fpath)
    else:
        data = request.get_json(silent=True) or {}
        file_paths = data.get("file_paths", [])
        document_texts = data.get("documents", [])
        include_web = data.get("include_web_research", True)
        fast_mode = data.get("fast_mode", True)

    if not file_paths and not document_texts:
        return jsonify({"error": "Provide file_paths or documents"}), 400

    result = market_intelligence_tool(
        document_paths=file_paths or None,
        document_texts=document_texts or None,
        include_web_research=include_web,
        fast_mode=fast_mode,
        save_output=True,
    )
    status_code = 200 if result.get("success") else 422
    return jsonify(result), status_code


@main_bp.route("/api/itinerary/recommendations", methods=["POST"])
def api_itinerary_recommendations():
    """
    Generate strategic recommendations from itinerary analyses.

    Body: {
        "itineraries": [{"name": "...", "analysis": {...}}, ...],
        "language": "English"
    }
    """
    from tools.itinerary_tools import generate_recommendations_tool

    data = request.get_json(silent=True) or {}
    itinerary_data = data.get("itineraries", [])
    language = data.get("language", "English")

    if not itinerary_data:
        return jsonify({"error": "Provide itineraries with analysis data"}), 400

    result = generate_recommendations_tool(itinerary_data, language, save_output=True)
    status_code = 200 if result.get("status") == "success" else 422
    return jsonify(result), status_code


@main_bp.route("/api/itinerary/extract-pdf", methods=["POST"])
def api_extract_pdf():
    """
    Extract raw text from a PDF file (itinerary-optimised).

    Upload a PDF or provide {"file_path": "..."}.
    Returns text with Thai/price/table detection and quality score.
    """
    from tools.itinerary_tools import extract_pdf_text_tool

    filepath = _resolve_itinerary_file(request)
    if isinstance(filepath, tuple):
        return filepath

    result = extract_pdf_text_tool(filepath)
    status_code = 200 if result.get("success") else 422
    return jsonify(result), status_code


def _resolve_itinerary_file(req):
    """Helper to extract file path from upload or JSON body."""
    if "file" in req.files:
        f = req.files["file"]
        os.makedirs(Config.ITINERARY_UPLOAD_DIR, exist_ok=True)
        fname = secure_filename(f.filename)
        fpath = os.path.join(Config.ITINERARY_UPLOAD_DIR, f"{uuid.uuid4().hex[:8]}_{fname}")
        f.save(fpath)
        return fpath
    else:
        data = req.get_json(silent=True) or {}
        fpath = data.get("file_path", "")
        if not fpath or not os.path.exists(fpath):
            return jsonify({"error": "File not found. Upload a file or provide file_path."}), 400
        return fpath


@main_bp.route("/api/program-code/<tour_code>", methods=["GET"])
def api_find_program_code(tour_code: str):
    """Find program code for a given tour code. Called by n8n."""
    # This would search the website for the program code
    # For now, return the tour code as-is (to be enhanced with actual lookup)
    return jsonify({
        "tour_code": tour_code,
        "program_code": tour_code,
        "note": "Auto-detected from tour code",
    })


@main_bp.route("/api/callback", methods=["POST"])
def api_callback():
    """
    Callback endpoint for n8n to report workflow results.

    Body: {
        "job_id": "...",
        "callback_secret": "...",
        "results": [ ... ]
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    # Verify callback secret
    if data.get("callback_secret") != Config.N8N_CALLBACK_SECRET:
        return jsonify({"error": "Invalid callback secret"}), 403

    job_id = data.get("job_id")
    results = data.get("results", [])

    logger.info(f"n8n callback received for job {job_id}: {len(results)} results")

    # Store results and notify connected WebSocket clients
    from services.expense_service import _jobs
    if job_id in _jobs:
        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["results"] = results

    # Broadcast result to WebSocket
    try:
        from app import socketio
        success = sum(1 for r in results if r.get("status") == "success")
        failed = len(results) - success

        summary = f"## n8n Workflow Complete\n\n"
        summary += f"**Job:** `{job_id}`\n"
        summary += f"**Results:** {success} successful, {failed} failed out of {len(results)} records\n\n"

        for r in results:
            status_icon = "OK" if r.get("status") == "success" else "FAIL"
            summary += f"- [{status_icon}] `{r.get('tour_code', 'N/A')}`: {r.get('expense_number', r.get('error', ''))}\n"

        socketio.emit("agent_response", {
            "type": "response",
            "content": summary,
            "agent": "n8n Workflow",
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        logger.warning(f"Could not broadcast callback result: {e}")

    return jsonify({"status": "received", "job_id": job_id})


@main_bp.route("/api/jobs/<job_id>", methods=["GET"])
def api_job_status(job_id: str):
    """Check the status of a processing job."""
    from services.expense_service import get_job
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)

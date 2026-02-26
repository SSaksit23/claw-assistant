"""
WebSocket event handlers for real-time chat communication.

Every user message is routed through the Assignment Agent. The agent
decides whether it can reply directly or must delegate to a specialist.

CRITICAL: All slow work (OpenAI calls, browser automation) runs in
background tasks via socketio.start_background_task() so the WebSocket
heartbeat is never blocked.
"""

import logging
from datetime import datetime

from flask_socketio import emit, disconnect
from flask import request, session as flask_session

from app import socketio
from services import learning_service

logger = logging.getLogger(__name__)

sessions = {}


@socketio.on("connect")
def handle_connect():
    if not flask_session.get("authenticated"):
        logger.warning("Unauthenticated WebSocket connection rejected")
        disconnect()
        return False

    sid = request.sid
    sessions[sid] = {
        "id": sid,
        "connected_at": datetime.utcnow().isoformat(),
        "messages": [],
        "session_id": flask_session.get("session_id", "default"),
        "website_username": flask_session.get("website_username", ""),
        "website_password": flask_session.get("website_password", ""),
    }
    username = flask_session.get("website_username", "unknown")
    logger.info("Client connected: %s (user=%s, session=%s)", sid, username, sessions[sid]["session_id"])
    emit("system_message", {
        "type": "system",
        "content": f"Connected to Web365 ClawBot. Signed in as **{username}**.",
        "timestamp": datetime.utcnow().isoformat(),
    })


@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    sessions.pop(sid, None)
    logger.info(f"Client disconnected: {sid}")


@socketio.on("user_message")
def handle_user_message(data):
    """
    Receive the message, immediately acknowledge, then dispatch
    all heavy processing to a background greenlet.
    """
    sid = request.sid
    message = data.get("message", "").strip()
    file_path = data.get("file_path")
    expense_type = data.get("expense_type", "")

    if not message and not file_path:
        emit("agent_response", {
            "type": "error",
            "content": "Please enter a message or upload a file.",
            "timestamp": datetime.utcnow().isoformat(),
        })
        return

    logger.info("[%s] message=%s  file=%s  expense_type=%s", sid, _safe(message, 60), file_path, expense_type)

    # Store in history
    session = sessions.get(sid, {"messages": []})
    session["messages"].append({
        "role": "user",
        "content": message or f"[uploaded file: {file_path}]",
        "timestamp": datetime.utcnow().isoformat(),
    })

    # Persist expense_type in session so it carries across messages
    if expense_type:
        session["expense_type"] = expense_type

    # Check if the expense service is waiting for a user answer
    user_session_id = session.get("session_id", "default")
    if message and not file_path:
        from services.expense_service import has_pending_input, submit_user_input
        if has_pending_input(user_session_id):
            logger.info("[%s] Routing reply to pending expense input: %s", sid, _safe(message, 60))
            submit_user_input(user_session_id, message)
            return

    # Check if there is a pending invoice review awaiting confirmation
    if message and not file_path:
        from services.expense_service import has_pending_review
        if has_pending_review(user_session_id):
            logger.info("[%s] Pending invoice review found, routing to confirm handler", sid)
            emit("agent_status", {
                "agent": "Accounting Agent",
                "status": "thinking",
                "message": "Processing your response...",
            })
            website_username = session.get("website_username", "")
            website_password = session.get("website_password", "")
            current_expense_type = session.get("expense_type", "")
            socketio.start_background_task(
                _handle_review_response,
                sid, message, user_session_id,
                website_username, website_password,
                current_expense_type,
            )
            return

    # Show thinking immediately
    emit("agent_status", {
        "agent": "Assignment Agent",
        "status": "thinking",
        "message": "Understanding your request...",
    })

    user_session_id = session.get("session_id", "default")
    website_username = session.get("website_username", "")
    website_password = session.get("website_password", "")
    current_expense_type = session.get("expense_type", "")

    socketio.start_background_task(
        _process_in_background,
        sid,
        message,
        file_path,
        list(session["messages"][-12:]),
        user_session_id,
        website_username,
        website_password,
        current_expense_type,
    )


# ── background worker ──────────────────────────────────────────────────────

def _process_in_background(sid, message, file_path, history,
                           user_session_id="default",
                           website_username="", website_password="",
                           expense_type=""):
    """
    Runs on a separate eventlet greenlet. Uses socketio.emit() (server-side)
    instead of flask-socketio's context-aware emit() because we're outside
    the request context.
    """
    def _emit(event, data):
        socketio.emit(event, data, to=sid)

    try:
        from agents.assignment_agent import process_message, delegate, INTENTS

        session = sessions.get(sid, {})

        # ── Handle type-button click: "[TYPE:flight] Air ticket selected" ──
        if message.startswith("[TYPE:"):
            pending_file = session.get("pending_file_path")
            if pending_file:
                task_details = session.pop("pending_task_details", {})
                session.pop("pending_file_path", None)
                _emit("agent_progress", {
                    "agent": "Assignment Agent",
                    "message": "Handing off to **Accounting Agent**...",
                })
                specialist_result = delegate(
                    intent="expense_recording",
                    task_details=task_details,
                    file_path=pending_file,
                    emit_fn=_emit,
                    session_id=user_session_id,
                    website_username=website_username,
                    website_password=website_password,
                    expense_type=expense_type,
                )
                if specialist_result and specialist_result.get("review_pending"):
                    _emit("expense_review", {
                        "content": specialist_result["content"],
                        "agent": "Accounting Agent",
                        "job_id": specialist_result.get("job_id"),
                        "data": specialist_result.get("data"),
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                elif specialist_result and specialist_result.get("content"):
                    session.pop("expense_type", None)
                    _emit("agent_response", {
                        "type": "response",
                        "content": specialist_result["content"],
                        "agent": "Accounting Agent",
                        "data": specialist_result.get("data"),
                        "timestamp": datetime.utcnow().isoformat(),
                    })
            else:
                # Type selected but no file yet → ask user to upload
                _emit("agent_response", {
                    "type": "response",
                    "content": "Got it! Now please **upload the expense file** to continue.",
                    "agent": "Assignment Agent",
                    "timestamp": datetime.utcnow().isoformat(),
                })
            _emit("agent_status", {
                "agent": "Assignment Agent",
                "status": "idle",
                "message": "Ready",
            })
            return

        # ── If expense_type is already set and user uploads a file, go to review ──
        if expense_type and file_path:
            _emit("agent_progress", {
                "agent": "Assignment Agent",
                "message": "Handing off to **Accounting Agent**...",
            })
            task_details = session.get("pending_task_details", {})
            session.pop("pending_task_details", None)
            session.pop("pending_file_path", None)

            specialist_result = delegate(
                intent="expense_recording",
                task_details=task_details,
                file_path=file_path,
                emit_fn=_emit,
                session_id=user_session_id,
                website_username=website_username,
                website_password=website_password,
                expense_type=expense_type,
            )
            if specialist_result and specialist_result.get("review_pending"):
                _emit("expense_review", {
                    "content": specialist_result["content"],
                    "agent": "Accounting Agent",
                    "job_id": specialist_result.get("job_id"),
                    "data": specialist_result.get("data"),
                    "timestamp": datetime.utcnow().isoformat(),
                })
            elif specialist_result and specialist_result.get("content"):
                session.pop("expense_type", None)
                _emit("agent_response", {
                    "type": "response",
                    "content": specialist_result["content"],
                    "agent": "Accounting Agent",
                    "data": specialist_result.get("data"),
                    "timestamp": datetime.utcnow().isoformat(),
                })
            _emit("agent_status", {
                "agent": "Assignment Agent",
                "status": "idle",
                "message": "Ready",
            })
            return

        # ── Step 1: Assignment Agent classifies ──
        classification = process_message(
            message=message,
            file_path=file_path,
            history=history,
        )

        intent = classification.get("intent", "general")
        response_text = classification.get("response", "")
        should_delegate = classification.get("delegate", False)
        task_details = classification.get("task_details", {})
        agent_name = INTENTS.get(intent, {}).get("agent", "Assignment Agent")

        # ── Expense recording: show type-selection buttons before proceeding ──
        if intent == "expense_recording" and should_delegate and not expense_type:
            _emit("agent_response", {
                "type": "response",
                "content": response_text,
                "agent": "Assignment Agent",
                "timestamp": datetime.utcnow().isoformat(),
            })
            _emit("type_selection", {
                "prompt": "Please select the **expense type**:",
                "agent": "Assignment Agent",
            })
            # Store any file that was uploaded along with this message
            if file_path:
                session["pending_file_path"] = file_path
            session["pending_task_details"] = task_details
            _emit("agent_status", {
                "agent": "Assignment Agent",
                "status": "idle",
                "message": "Waiting for type selection",
            })
            return

        # Send the Assignment Agent's reply
        _emit("agent_response", {
            "type": "response",
            "content": response_text,
            "agent": "Assignment Agent",
            "timestamp": datetime.utcnow().isoformat(),
        })

        _emit("agent_status", {
            "agent": "Assignment Agent",
            "status": "idle",
            "message": "Ready",
        })

        # Store assistant turn
        if response_text:
            session.setdefault("messages", []).append({
                "role": "assistant",
                "content": response_text,
            })

        # ── Step 2: Delegate if needed ──
        if should_delegate and intent != "general":
            _emit("agent_progress", {
                "agent": "Assignment Agent",
                "message": f"Handing off to **{agent_name}**...",
            })

            specialist_result = delegate(
                intent=intent,
                task_details=task_details,
                file_path=file_path,
                emit_fn=_emit,
                session_id=user_session_id,
                website_username=website_username,
                website_password=website_password,
                expense_type=expense_type,
            )

            if specialist_result and specialist_result.get("review_pending"):
                _emit("expense_review", {
                    "content": specialist_result["content"],
                    "agent": agent_name,
                    "job_id": specialist_result.get("job_id"),
                    "data": specialist_result.get("data"),
                    "timestamp": datetime.utcnow().isoformat(),
                })
            elif specialist_result and specialist_result.get("content"):
                session.pop("expense_type", None)
                _emit("agent_response", {
                    "type": "response",
                    "content": specialist_result["content"],
                    "agent": agent_name,
                    "data": specialist_result.get("data"),
                    "timestamp": datetime.utcnow().isoformat(),
                })

    except Exception as e:
        logger.error(f"Background processing failed: {e}", exc_info=True)
        learning_service.log_error(
            agent="System",
            error_type="background_processing",
            summary="Background task processing failed",
            error_message=str(e),
            context=f"Message: {message[:200] if message else 'N/A'}, File: {file_path}",
            related_files=["app/websocket.py"],
        )
        _emit("agent_response", {
            "type": "error",
            "content": f"An error occurred: {str(e)}",
            "timestamp": datetime.utcnow().isoformat(),
        })
        _emit("agent_status", {
            "agent": "Assignment Agent",
            "status": "idle",
            "message": "Ready",
        })


@socketio.on("expense_review_confirm")
def handle_expense_review_confirm(data):
    """User clicked confirm on the invoice review."""
    sid = request.sid
    session = sessions.get(sid, {})
    company_name = data.get("company_name", "")
    code_group_overrides = data.get("code_group_overrides", None)
    user_session_id = session.get("session_id", "default")
    website_username = session.get("website_username", "")
    website_password = session.get("website_password", "")
    expense_type = session.get("expense_type", "")

    logger.info("[%s] expense_review_confirm company=%s overrides=%s",
                sid, company_name[:40], code_group_overrides)

    emit("agent_status", {
        "agent": "Accounting Agent",
        "status": "working",
        "message": "Starting expense recording...",
    })

    socketio.start_background_task(
        _execute_confirmed_review,
        sid, user_session_id, company_name,
        website_username, website_password, expense_type,
        code_group_overrides,
    )


def _execute_confirmed_review(sid, session_id, company_name,
                              website_username, website_password, expense_type,
                              code_group_overrides=None):
    """Background worker: execute the confirmed invoice review."""
    def _emit(event, data):
        socketio.emit(event, data, to=sid)

    try:
        from services.expense_service import confirm_and_execute_expense

        result = confirm_and_execute_expense(
            session_id=session_id,
            emit_fn=_emit,
            company_name=company_name,
            website_username=website_username,
            website_password=website_password,
            expense_type=expense_type,
            code_group_overrides=code_group_overrides,
        )

        session = sessions.get(sid, {})
        session.pop("expense_type", None)

        if result and result.get("content"):
            _emit("agent_response", {
                "type": "response",
                "content": result["content"],
                "agent": "Accounting Agent",
                "data": result.get("data"),
                "timestamp": datetime.utcnow().isoformat(),
            })

    except Exception as e:
        logger.error("Confirmed review execution failed: %s", e, exc_info=True)
        _emit("agent_response", {
            "type": "error",
            "content": f"An error occurred during expense recording: {str(e)}",
            "timestamp": datetime.utcnow().isoformat(),
        })

    _emit("agent_status", {
        "agent": "Accounting Agent",
        "status": "idle",
        "message": "Ready",
    })


def _handle_review_response(sid, message, session_id,
                            website_username, website_password, expense_type):
    """
    Background worker: handle a text message while an invoice review is pending.
    Detects confirmation keywords or treats the message as company name + confirm.
    """
    def _emit(event, data):
        socketio.emit(event, data, to=sid)

    try:
        from services.expense_service import (
            has_pending_review, get_pending_review,
            confirm_and_execute_expense, _pending_reviews, _review_lock,
        )

        msg_lower = message.strip().lower()
        confirm_keywords = {"confirm", "yes", "ok", "proceed", "go", "ยืนยัน", "ตกลง", "确认", "好"}
        is_confirm = msg_lower in confirm_keywords

        pending = get_pending_review(session_id)
        if not pending:
            _emit("agent_response", {
                "type": "response",
                "content": "No pending review found.",
                "agent": "Accounting Agent",
                "timestamp": datetime.utcnow().isoformat(),
            })
            return

        company_name = pending.get("company_name", "")

        if is_confirm and company_name:
            # Confirmed with company already set
            pass
        elif is_confirm and not company_name:
            _emit("agent_response", {
                "type": "response",
                "content": "Please provide the **company name** before confirming "
                           "(e.g., `Go365Travel` or `2U Center`).",
                "agent": "Accounting Agent",
                "timestamp": datetime.utcnow().isoformat(),
            })
            _emit("agent_status", {
                "agent": "Accounting Agent",
                "status": "idle",
                "message": "Waiting for company name",
            })
            return
        else:
            # Treat the message as company name and auto-confirm
            company_name = message.strip()
            with _review_lock:
                if session_id in _pending_reviews:
                    _pending_reviews[session_id]["company_name"] = company_name
            _emit("agent_progress", {
                "agent": "Accounting Agent",
                "message": f"Company set to **{company_name}**. Proceeding...",
            })

        result = confirm_and_execute_expense(
            session_id=session_id,
            emit_fn=_emit,
            company_name=company_name,
            website_username=website_username,
            website_password=website_password,
            expense_type=expense_type,
        )

        session = sessions.get(sid, {})
        session.pop("expense_type", None)

        if result and result.get("content"):
            _emit("agent_response", {
                "type": "response",
                "content": result["content"],
                "agent": "Accounting Agent",
                "data": result.get("data"),
                "timestamp": datetime.utcnow().isoformat(),
            })

    except Exception as e:
        logger.error("Review response handling failed: %s", e, exc_info=True)
        _emit("agent_response", {
            "type": "error",
            "content": f"An error occurred: {str(e)}",
            "timestamp": datetime.utcnow().isoformat(),
        })

    _emit("agent_status", {
        "agent": "Accounting Agent",
        "status": "idle",
        "message": "Ready",
    })


@socketio.on("user_feedback")
def handle_user_feedback(data):
    """Handle explicit user feedback/corrections to improve agent learning."""
    feedback_type = data.get("type", "correction")
    content = data.get("content", "")
    context = data.get("context", "")

    if not content:
        return

    if feedback_type == "correction":
        learning_service.log_learning(
            agent="User Feedback",
            category="correction",
            summary=content[:200],
            details=f"User correction: {content}\nContext: {context}",
            suggested_action="Apply this correction in future similar tasks",
            priority="high",
            tags=["user_feedback", "correction"],
        )
    elif feedback_type == "feature_request":
        learning_service.log_feature_request(
            agent="User Feedback",
            capability=content[:200],
            user_context=context,
        )

    emit("system_message", {
        "type": "system",
        "content": "Thank you for your feedback! I'll remember this for next time.",
        "timestamp": datetime.utcnow().isoformat(),
    })


def _safe(text, maxlen=80):
    """Truncate and make text safe for logging."""
    if not text:
        return ""
    safe = text.encode("ascii", errors="replace").decode("ascii")
    return safe[:maxlen]

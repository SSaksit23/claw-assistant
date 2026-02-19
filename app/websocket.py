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

from flask_socketio import emit
from flask import request

from app import socketio
from services import learning_service

logger = logging.getLogger(__name__)

sessions = {}


@socketio.on("connect")
def handle_connect():
    sid = request.sid
    sessions[sid] = {
        "id": sid,
        "connected_at": datetime.utcnow().isoformat(),
        "messages": [],
    }
    logger.info(f"Client connected: {sid}")
    emit("system_message", {
        "type": "system",
        "content": "Connected to Web365 ClawBot.",
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

    if not message and not file_path:
        emit("agent_response", {
            "type": "error",
            "content": "Please enter a message or upload a file.",
            "timestamp": datetime.utcnow().isoformat(),
        })
        return

    logger.info("[%s] message=%s  file=%s", sid, _safe(message, 60), file_path)

    # Store in history
    session = sessions.get(sid, {"messages": []})
    session["messages"].append({
        "role": "user",
        "content": message or f"[uploaded file: {file_path}]",
        "timestamp": datetime.utcnow().isoformat(),
    })

    # Show thinking immediately
    emit("agent_status", {
        "agent": "Assignment Agent",
        "status": "thinking",
        "message": "Understanding your request...",
    })

    # Hand off ALL processing to a background greenlet.
    # This returns control to eventlet so heartbeats keep flowing.
    socketio.start_background_task(
        _process_in_background,
        sid,
        message,
        file_path,
        list(session["messages"][-12:]),
    )


# ── background worker ──────────────────────────────────────────────────────

def _process_in_background(sid, message, file_path, history):
    """
    Runs on a separate eventlet greenlet. Uses socketio.emit() (server-side)
    instead of flask-socketio's context-aware emit() because we're outside
    the request context.
    """
    def _emit(event, data):
        socketio.emit(event, data, to=sid)

    try:
        from agents.assignment_agent import process_message, delegate, INTENTS

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
        session = sessions.get(sid)
        if session:
            session["messages"].append({
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
            )

            if specialist_result and specialist_result.get("content"):
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

"""
Learning Service -- Self-improving agent memory system.

Inspired by the self-improving-agent pattern (clawhub.ai/pskoett/self-improving-agent).
Agents log learnings, errors, and feature requests to markdown files.
Before performing tasks, agents consult past learnings to avoid repeating mistakes
and apply best practices.

Files:
  .learnings/LEARNINGS.md  -- corrections, knowledge gaps, best practices
  .learnings/ERRORS.md     -- command failures, exceptions
  .learnings/FEATURE_REQUESTS.md -- user-requested capabilities
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

LEARNINGS_DIR = Path(__file__).parent.parent / ".learnings"
LEARNINGS_FILE = LEARNINGS_DIR / "LEARNINGS.md"
ERRORS_FILE = LEARNINGS_DIR / "ERRORS.md"
FEATURES_FILE = LEARNINGS_DIR / "FEATURE_REQUESTS.md"


def _ensure_dir():
    LEARNINGS_DIR.mkdir(exist_ok=True)


def _next_id(prefix: str, filepath: Path) -> str:
    """Generate next sequential ID like LRN-20260219-001."""
    date_str = datetime.now().strftime("%Y%m%d")
    base = f"{prefix}-{date_str}-"
    count = 1
    if filepath.exists():
        content = filepath.read_text(encoding="utf-8")
        import re
        existing = re.findall(rf"{re.escape(base)}(\d{{3}})", content)
        if existing:
            count = max(int(x) for x in existing) + 1
    return f"{base}{count:03d}"


def log_learning(
    agent: str,
    category: str,
    summary: str,
    details: str,
    suggested_action: str = "",
    area: str = "backend",
    priority: str = "medium",
    related_files: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
):
    """Log a learning entry (correction, knowledge gap, or best practice)."""
    _ensure_dir()
    entry_id = _next_id("LRN", LEARNINGS_FILE)
    now = datetime.now().isoformat()

    entry = f"""
## [{entry_id}] {category}

**Logged**: {now}
**Agent**: {agent}
**Priority**: {priority}
**Status**: pending
**Area**: {area}

### Summary
{summary}

### Details
{details}

### Suggested Action
{suggested_action or 'Review and apply in future tasks.'}

### Metadata
- Source: agent_operation
- Related Files: {', '.join(related_files) if related_files else 'N/A'}
- Tags: {', '.join(tags) if tags else category}

---
"""
    with open(LEARNINGS_FILE, "a", encoding="utf-8") as f:
        f.write(entry)
    logger.info("Learning logged: %s - %s", entry_id, summary[:80])
    return entry_id


def log_error(
    agent: str,
    error_type: str,
    summary: str,
    error_message: str,
    context: str = "",
    suggested_fix: str = "",
    area: str = "backend",
    priority: str = "high",
    related_files: Optional[list[str]] = None,
):
    """Log an error entry."""
    _ensure_dir()
    entry_id = _next_id("ERR", ERRORS_FILE)
    now = datetime.now().isoformat()

    entry = f"""
## [{entry_id}] {error_type}

**Logged**: {now}
**Agent**: {agent}
**Priority**: {priority}
**Status**: pending
**Area**: {area}

### Summary
{summary}

### Error
```
{error_message}
```

### Context
{context or 'During automated task execution.'}

### Suggested Fix
{suggested_fix or 'Investigate and fix the root cause.'}

### Metadata
- Reproducible: unknown
- Related Files: {', '.join(related_files) if related_files else 'N/A'}

---
"""
    with open(ERRORS_FILE, "a", encoding="utf-8") as f:
        f.write(entry)
    logger.info("Error logged: %s - %s", entry_id, summary[:80])
    return entry_id


def log_feature_request(
    agent: str,
    capability: str,
    user_context: str,
    complexity: str = "medium",
    suggested_implementation: str = "",
    area: str = "backend",
):
    """Log a feature request."""
    _ensure_dir()
    entry_id = _next_id("FEAT", FEATURES_FILE)
    now = datetime.now().isoformat()

    entry = f"""
## [{entry_id}] {capability}

**Logged**: {now}
**Agent**: {agent}
**Priority**: medium
**Status**: pending
**Area**: {area}

### Requested Capability
{capability}

### User Context
{user_context}

### Complexity Estimate
{complexity}

### Suggested Implementation
{suggested_implementation or 'To be determined.'}

### Metadata
- Frequency: first_time

---
"""
    with open(FEATURES_FILE, "a", encoding="utf-8") as f:
        f.write(entry)
    logger.info("Feature request logged: %s - %s", entry_id, capability[:80])
    return entry_id


def get_learnings(
    agent: Optional[str] = None,
    category: Optional[str] = None,
    area: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """Retrieve recent learnings, optionally filtered.

    Returns a list of dicts with id, category, summary, details, suggested_action.
    """
    if not LEARNINGS_FILE.exists():
        return []

    content = LEARNINGS_FILE.read_text(encoding="utf-8")
    return _parse_entries(content, agent=agent, category=category, area=area, limit=limit)


def get_errors(
    agent: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """Retrieve recent errors, optionally filtered by agent."""
    if not ERRORS_FILE.exists():
        return []

    content = ERRORS_FILE.read_text(encoding="utf-8")
    return _parse_entries(content, agent=agent, limit=limit)


def get_relevant_learnings(task_description: str, agent: str = None, limit: int = 5) -> str:
    """Get a summary of relevant learnings for a task, formatted for LLM context.

    This is the key function agents call before performing tasks to consult
    past experience and avoid repeating mistakes.
    """
    learnings = get_learnings(agent=agent, limit=30)
    errors = get_errors(agent=agent, limit=20)

    if not learnings and not errors:
        return ""

    task_lower = task_description.lower()
    keywords = set(task_lower.split())

    def relevance_score(entry: dict) -> int:
        score = 0
        text = f"{entry.get('summary', '')} {entry.get('details', '')} {entry.get('tags', '')}".lower()
        for kw in keywords:
            if len(kw) > 3 and kw in text:
                score += 1
        if entry.get("priority") == "critical":
            score += 3
        elif entry.get("priority") == "high":
            score += 2
        return score

    scored_learnings = [(relevance_score(l), l) for l in learnings]
    scored_errors = [(relevance_score(e), e) for e in errors]

    top_learnings = sorted(scored_learnings, key=lambda x: x[0], reverse=True)[:limit]
    top_errors = sorted(scored_errors, key=lambda x: x[0], reverse=True)[:limit]

    parts = []
    if any(score > 0 for score, _ in top_learnings):
        parts.append("**Past Learnings:**")
        for score, l in top_learnings:
            if score > 0:
                parts.append(f"- [{l.get('id', '?')}] {l.get('summary', '')} -> {l.get('suggested_action', '')}")

    if any(score > 0 for score, _ in top_errors):
        parts.append("\n**Known Issues:**")
        for score, e in top_errors:
            if score > 0:
                parts.append(f"- [{e.get('id', '?')}] {e.get('summary', '')} -> {e.get('suggested_fix', '')}")

    return "\n".join(parts) if parts else ""


def _parse_entries(
    content: str,
    agent: Optional[str] = None,
    category: Optional[str] = None,
    area: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """Parse markdown entries into structured dicts."""
    import re
    entries = []
    blocks = re.split(r'\n## \[', content)

    for block in blocks[1:]:
        entry = {}
        id_match = re.match(r'([A-Z]+-\d{8}-\d{3})\]\s*(.*)', block)
        if id_match:
            entry["id"] = id_match.group(1)
            entry["category"] = id_match.group(2).strip()

        for field, pattern in [
            ("agent", r'\*\*Agent\*\*:\s*(.+)'),
            ("priority", r'\*\*Priority\*\*:\s*(.+)'),
            ("status", r'\*\*Status\*\*:\s*(.+)'),
            ("area", r'\*\*Area\*\*:\s*(.+)'),
        ]:
            m = re.search(pattern, block)
            if m:
                entry[field] = m.group(1).strip()

        summary_match = re.search(r'### Summary\n(.+?)(?=\n###|\n---|\Z)', block, re.DOTALL)
        if summary_match:
            entry["summary"] = summary_match.group(1).strip()

        details_match = re.search(r'### Details\n(.+?)(?=\n###|\n---|\Z)', block, re.DOTALL)
        if details_match:
            entry["details"] = details_match.group(1).strip()

        action_match = re.search(r'### Suggested (?:Action|Fix)\n(.+?)(?=\n###|\n---|\Z)', block, re.DOTALL)
        if action_match:
            entry["suggested_action"] = action_match.group(1).strip()
            entry["suggested_fix"] = action_match.group(1).strip()

        tags_match = re.search(r'- Tags:\s*(.+)', block)
        if tags_match:
            entry["tags"] = tags_match.group(1).strip()

        if agent and entry.get("agent", "").lower() != agent.lower():
            continue
        if category and entry.get("category", "").lower() != category.lower():
            continue
        if area and entry.get("area", "").lower() != area.lower():
            continue

        entries.append(entry)

    return entries[-limit:] if len(entries) > limit else entries


def resolve_entry(entry_id: str, notes: str = "", commit_ref: str = ""):
    """Mark a learning or error entry as resolved."""
    for filepath in [LEARNINGS_FILE, ERRORS_FILE, FEATURES_FILE]:
        if not filepath.exists():
            continue
        content = filepath.read_text(encoding="utf-8")
        if entry_id not in content:
            continue

        now = datetime.now().isoformat()
        resolution = f"""
### Resolution
- **Resolved**: {now}
- **Commit/PR**: {commit_ref or 'N/A'}
- **Notes**: {notes or 'Resolved.'}
"""
        content = content.replace(
            f"**Status**: pending",
            f"**Status**: resolved",
            1,
        )
        import re
        pattern = rf'(\[{re.escape(entry_id)}\].*?)(---)'
        content = re.sub(pattern, rf'\1{resolution}\n\2', content, count=1, flags=re.DOTALL)

        filepath.write_text(content, encoding="utf-8")
        logger.info("Resolved entry: %s", entry_id)
        return True

    return False

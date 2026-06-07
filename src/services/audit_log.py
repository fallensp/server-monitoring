"""Local audit trail for control actions taken from the dashboard.

Actions are appended to a JSONL file next to the project so there is a
permanent record of who did what from the dashboard, even across restarts.
"""

import getpass
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

AUDIT_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "action_audit.jsonl"

_write_lock = threading.Lock()


def log_action(
    resource_type: str,
    resource_id: str,
    action: str,
    region: str,
    success: bool,
    message: str = "",
) -> dict:
    """Append a control action to the audit log.

    Args:
        resource_type: "EC2" or "RDS"
        resource_id: Instance ID or DB identifier
        action: "start", "stop", "reboot"
        region: AWS region
        success: Whether the API call succeeded
        message: Result or error message

    Returns:
        The logged entry dict
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": getpass.getuser(),
        "resource_type": resource_type,
        "resource_id": resource_id,
        "action": action,
        "region": region,
        "success": success,
        "message": message,
    }
    with _write_lock:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    return entry


def read_actions(limit: int = 50) -> list[dict]:
    """Read the most recent audit log entries, newest first."""
    if not AUDIT_LOG_PATH.exists():
        return []
    entries = []
    with open(AUDIT_LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries[::-1][:limit]

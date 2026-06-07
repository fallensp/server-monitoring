"""Stopped-RDS auto-restart watchdog.

AWS automatically restarts manually-stopped RDS instances after 7 days.
This module finds when each stopped instance was stopped (via RDS events,
which only go back 14 days) and persists stop times to a local registry so
countdowns survive beyond the event window and across stop/restart cycles.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

from src.aws.client import get_client

REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / ".rds_stop_registry.json"

AUTO_RESTART_DAYS = 7
EVENT_LOOKBACK_MINUTES = 20160  # 14 days — the describe_events maximum


def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {}
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_registry(registry: dict) -> None:
    try:
        REGISTRY_PATH.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    except OSError:
        pass


def find_stop_time_from_events(db_id: str, region: str) -> datetime | None:
    """Find the most recent 'DB instance stopped' event for an instance."""
    try:
        rds = get_client("rds", region)
        resp = rds.describe_events(
            SourceIdentifier=db_id,
            SourceType="db-instance",
            Duration=EVENT_LOOKBACK_MINUTES,
        )
    except (ClientError, BotoCoreError):
        return None

    stop_events = [
        e["Date"] for e in resp.get("Events", [])
        if "stopped" in e.get("Message", "").lower()
    ]
    return max(stop_events) if stop_events else None


def get_restart_countdowns(rds_instances: list[dict]) -> list[dict]:
    """Compute auto-restart countdowns for all stopped RDS instances.

    Args:
        rds_instances: RDS instance dicts with Identifier/Region/Status keys
            (the shape used by app_v2). Non-stopped instances are used only
            to prune stale registry entries.

    Returns:
        One dict per stopped instance:
        {db_id, region, stop_time, restart_eta, remaining: timedelta|None}
    """
    registry = _load_registry()
    changed = False
    now = datetime.now(timezone.utc)
    countdowns = []
    stopped_keys = set()

    for inst in rds_instances:
        db_id = inst.get("Identifier", "")
        region = inst.get("Region", "")
        status = inst.get("Status", "")
        key = f"{region}:{db_id}"

        if status != "stopped":
            continue
        stopped_keys.add(key)

        registry_time = None
        if key in registry:
            try:
                registry_time = datetime.fromisoformat(registry[key])
            except ValueError:
                registry_time = None

        # Always check events too and keep the NEWEST stop time: after a
        # stop -> auto-restart -> stop cycle that happened while the
        # dashboard was closed, the registry would otherwise stay stale.
        event_time = find_stop_time_from_events(db_id, region)
        candidates = [t for t in (registry_time, event_time) if t is not None]
        stop_time = max(candidates) if candidates else None
        if stop_time is not None and (registry_time is None or stop_time > registry_time):
            registry[key] = stop_time.isoformat()
            changed = True

        restart_eta = stop_time + timedelta(days=AUTO_RESTART_DAYS) if stop_time else None
        countdowns.append({
            "db_id": db_id,
            "region": region,
            "stop_time": stop_time,
            "restart_eta": restart_eta,
            "remaining": (restart_eta - now) if restart_eta else None,
        })

    # Prune registry entries for instances that are no longer stopped, so a
    # future stop records a fresh timestamp instead of reusing a stale one.
    known_instances = {
        f"{inst.get('Region', '')}:{inst.get('Identifier', '')}"
        for inst in rds_instances
    }
    for key in list(registry):
        if key in known_instances and key not in stopped_keys:
            del registry[key]
            changed = True

    if changed:
        _save_registry(registry)

    return countdowns


def format_remaining(remaining: timedelta | None) -> str:
    """Format a countdown as 'Nd Nh' / 'Nh Nm' / 'overdue'."""
    if remaining is None:
        return "unknown"
    total_s = int(remaining.total_seconds())
    if total_s <= 0:
        return "overdue — may restart any time"
    days, rem = divmod(total_s, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

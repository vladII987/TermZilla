"""Connection history — stores recently visited hosts."""

import json
import logging
from pathlib import Path

logger = logging.getLogger("termzilla")

_HISTORY_PATH = Path.home() / ".config" / "termzilla" / "history.json"
_MAX_ENTRIES = 20


def load() -> list[dict]:
    """Return history list, most-recent first. Never raises."""
    try:
        if _HISTORY_PATH.exists():
            return json.loads(_HISTORY_PATH.read_text())
    except Exception as e:
        logger.warning(f"Could not load history: {e}")
    return []


def save(host: str, user: str, port: str, protocol: str = "sftp") -> None:
    """Prepend entry to history, dedup by host+user+protocol, trim to max size."""
    entries = load()
    entries = [
        e for e in entries
        if not (e.get("host") == host and e.get("user") == user and e.get("protocol", "sftp") == protocol)
    ]
    entries.insert(0, {"host": host, "user": user, "port": port, "protocol": protocol})
    entries = entries[:_MAX_ENTRIES]
    try:
        _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _HISTORY_PATH.write_text(json.dumps(entries, indent=2))
    except Exception as e:
        logger.warning(f"Could not save history: {e}")

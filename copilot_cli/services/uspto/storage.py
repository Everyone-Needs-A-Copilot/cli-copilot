"""Local storage helpers for USPTO sessions, dossiers, and watchlists."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def data_root() -> Path:
    """Return the local data directory for USPTO artifacts."""
    override = os.environ.get("COPILOT_USPTO_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".copilot-cli" / "uspto").resolve()


def ensure_dir(name: str) -> Path:
    path = data_root() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def record_path(kind: str, name: str) -> Path:
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in name).strip("-")
    if not safe_name:
        safe_name = "record"
    return ensure_dir(kind) / f"{safe_name}.json"


def save_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def list_records(kind: str) -> list[dict[str, Any]]:
    root = ensure_dir(kind)
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        data = load_json(path, default={}) or {}
        if isinstance(data, dict):
            data["_path"] = str(path)
            rows.append(data)
    return rows

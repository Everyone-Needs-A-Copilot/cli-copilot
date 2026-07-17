"""Log analysis — error pattern detection and rate calculation."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

ERROR_PATTERNS = [
    (r"(?i)error", "error"),
    (r"(?i)exception", "exception"),
    (r"(?i)fatal", "fatal"),
    (r"(?i)panic", "panic"),
    (r"(?i)failed", "failure"),
    (r"(?i)timeout", "timeout"),
    (r"(?i)refused", "connection_refused"),
    (r"(?i)out of memory|oom", "oom"),
    (r"(?i)permission denied", "permission_denied"),
    (r"(?i)disk full|no space", "disk_full"),
]


@dataclass
class LogAnalysis:
    total_lines: int = 0
    error_lines: int = 0
    error_rate: float = 0.0
    pattern_counts: dict[str, int] = field(default_factory=dict)
    recent_errors: list[str] = field(default_factory=list)
    top_errors: list[tuple[str, int]] = field(default_factory=list)


def extract_log_text(logs: Any) -> str:
    """Normalize the response shapes returned by Coolify log endpoints."""
    if isinstance(logs, str):
        return logs
    if isinstance(logs, dict):
        value = logs.get("logs", "")
        return value if isinstance(value, str) else str(value)
    if isinstance(logs, list):
        return "\n".join(item if isinstance(item, str) else str(item) for item in logs)
    return "" if logs is None else str(logs)


def analyze_logs(logs: str, max_recent: int = 10) -> LogAnalysis:
    """Analyze log text for error patterns."""
    result = LogAnalysis()
    lines = logs.strip().splitlines()
    result.total_lines = len(lines)

    pattern_counter: Counter[str] = Counter()
    error_lines: list[str] = []

    for line in lines:
        is_error = False
        for pattern, category in ERROR_PATTERNS:
            if re.search(pattern, line):
                pattern_counter[category] += 1
                is_error = True

        if is_error:
            error_lines.append(line.strip())

    result.error_lines = len(error_lines)
    result.error_rate = round(len(error_lines) / max(len(lines), 1) * 100, 2)
    result.pattern_counts = dict(pattern_counter)
    result.recent_errors = error_lines[-max_recent:]
    result.top_errors = pattern_counter.most_common(5)

    return result

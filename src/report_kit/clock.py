from __future__ import annotations

from datetime import datetime, timezone

from .constants import die

# Split out of env.py so that needing a timestamp does not also mean needing
# PyYAML installed. env.py is the only module in this package that requires a
# third-party package, and tools/export_metrics.py depends on that staying
# true: it is the path for re-exporting a window whose metrics are about to
# age out, so it has to keep working when the rest of the package can't load.


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_instant(text: str) -> datetime:
    try:
        return datetime.fromisoformat(
            text.strip().replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        die(f"bad timestamp: {text!r} (expected 2026-08-20T10:00:00Z)")


def hms(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:d}h{(seconds % 3600) // 60:02d}m{seconds % 60:02d}s"

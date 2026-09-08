from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

from .constants import die


class Env:
    """Addresses only. A missing key fails loudly rather than defaulting to
    something that happens to be reachable."""

    def __init__(self, path: Path):
        if not path.is_file():
            die(f"env file not found: {path}")
        self.path = path
        self.raw = yaml.safe_load(path.read_text()) or {}

    def get(self, dotted: str, default=None):
        node = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def need(self, dotted: str):
        value = self.get(dotted)
        if value in (None, "", [], {}) or (isinstance(value, str)
                                           and value.startswith("⟨")):
            die(f"{self.path}: unset or placeholder value: {dotted}")
        return value

    @property
    def namespace(self) -> str:
        return str(self.need("namespace"))

    def namespace_for(self, workload: str) -> str:
        """Per-workload override from `namespaces.<workload>`, falling back to
        the top-level `namespace`. The fallback is only correct when every
        workload this run touches really does live in one namespace."""
        return str(self.get(f"namespaces.{workload}", None) or self.namespace)

    @property
    def prom_url(self) -> str:
        return str(self.need("prometheus.url")).rstrip("/")

    @property
    def poll_seconds(self) -> float:
        """Float, not int: int() would turn a deliberate sub-second interval
        into 0 and busy-spin against the API server instead of polling it."""
        return float(self.get("poll_seconds", 15))

    @property
    def max_wait_seconds(self) -> float:
        return float(self.get("max_wait_seconds", 90 * 60))


def execution_dir(report_root: Path, execution: str) -> Path:
    """`<report_root>/executions/<execution>`. The root is passed in rather
    than derived from this file's location — a caller knows where its own
    report tree is; this package must not assume it sits at a fixed depth
    inside it."""
    return Path(report_root) / "executions" / execution

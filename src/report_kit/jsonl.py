from __future__ import annotations

import json
from pathlib import Path

from .constants import die

# Labels that identify the scrape target rather than what's being measured —
# dropped from the printed series label so a summary reads by what the
# series *is*, not which pod happened to report it.
NOISY_LABELS = {"instance", "job", "endpoint", "container", "__name__",
                 "namespace", "service", "pod"}


def load_lines(path: Path) -> list[dict]:
    """One JSON object per line, as prometheus.export_range() writes it:
    {"metric": ref, "query": …, "result": [ …Prometheus series… ]}."""
    if not path.is_file():
        die(f"not found: {path}")
    lines = []
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            lines.append(json.loads(raw))
        except json.JSONDecodeError as e:
            die(f"{path}:{lineno} not valid JSON: {e}")
    return lines


def parse_values(values: list) -> list[tuple[float, float]]:
    """Prometheus [timestamp, "value"] pairs -> (float, float); non-numeric and
    NaN samples dropped rather than raised on — a gap in the export, not a bug."""
    out = []
    for ts, raw in values:
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if v != v:  # NaN
            continue
        out.append((float(ts), v))
    return out


def label_summary(labels: dict) -> str:
    """Drops NOISY_LABELS, unless that would drop everything — an all-noisy
    series still deserves a label rather than "(no labels)"."""
    kept = {k: v for k, v in labels.items() if k not in NOISY_LABELS}
    if not kept:
        kept = labels
    return ", ".join(f"{k}={v}" for k, v in sorted(kept.items())) or "(no labels)"


def changes(values: list[tuple[float, float]]) -> list[float]:
    """Instants where the value differs from the sample before it.

    The point of having this is that a window usually contains two regimes —
    the system reacting, then the system settled — and a mean across both
    describes neither. Autoscaler replica count is the usual series to read
    them from: it is a fact in the export, so the split is exact rather than a
    guess about where "convergence" happened."""
    out = []
    for (_, previous), (timestamp, current) in zip(values, values[1:]):
        if current != previous:
            out.append(timestamp)
    return out


def split(values: list[tuple[float, float]], at: float
          ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """(before, from `at` onward). Splitting on the *last* change in a settling
    series gives the transient and the steady state; splitting on an earlier
    one gives two transients, which is rarely what anyone wants."""
    return ([p for p in values if p[0] < at], [p for p in values if p[0] >= at])

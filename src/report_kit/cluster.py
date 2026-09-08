from __future__ import annotations

from datetime import datetime

from . import shell
from .clock import parse_instant

# Karpenter-specific, and the distinction matters for validity. The three
# reasons below are the EC2 side taking an instance away involuntarily —
# that is what invalidates a measurement window. InstanceTerminating is
# *not* among them: Karpenter emits it for every teardown it decides on
# itself, consolidation included, and consolidation only ever disrupts a
# node already at pod-count 0. Counting it as an interruption marks healthy
# runs invalid (observed: nodes with that event had never had a workload
# pod scheduled to them). Use INTERRUPT_REASONS to see everything,
# FORCED_REASONS to judge validity.
FORCED_REASONS = [
    "SpotInterrupted",
    "TerminatingOnInterruption",
    "InstanceStopping",
]
INTERRUPT_REASONS = FORCED_REASONS + ["InstanceTerminating"]


def nodes_by_selector(selector: str) -> dict[str, str]:
    """name -> instance type."""
    data = shell.sh_json(["kubectl", "get", "nodes", "-l", selector, "-o", "json"])
    return {
        item["metadata"]["name"]:
            item.get("metadata", {}).get("labels", {}).get(
                "node.kubernetes.io/instance-type", "?")
        for item in data.get("items", [])
    }


def pods_by_node(namespace: str, label_selector: str) -> dict[str, list[str]]:
    """node -> running pod names. Whether a node that just vanished actually
    had anything on it — the real signal for whether its loss disrupted
    work — rather than whether the system had backlog somewhere else at the
    time (queue depth alone conflates the two, see FORCED_REASONS)."""
    data = shell.sh_json(["kubectl", "-n", namespace, "get", "pods",
                          "-l", label_selector,
                          "--field-selector=status.phase=Running", "-o", "json"])
    out: dict[str, list[str]] = {}
    for item in data.get("items", []):
        node = item.get("spec", {}).get("nodeName")
        if not node:
            continue
        out.setdefault(node, []).append(item["metadata"]["name"])
    return out


def deployment_replicas(namespace: str, name: str) -> int:
    data = shell.sh_json(["kubectl", "-n", namespace, "get", "deployment", name,
                          "-o", "json"])
    return int(data.get("status", {}).get("replicas", 0) or 0)


def interrupt_events(since: datetime) -> list[str]:
    """Best effort. Event TTL is short, so absence here proves nothing.

    Returns every matching event, InstanceTerminating included — the caller
    decides what counts against validity. Use `entry.split(' · ')[0] in
    FORCED_REASONS` to tell an involuntary loss from ordinary consolidation."""
    found = []
    try:
        data = shell.sh_json(["kubectl", "get", "events", "-A", "-o", "json"], timeout=45)
    except RuntimeError:
        return found
    for item in data.get("items", []):
        if item.get("reason", "") not in INTERRUPT_REASONS:
            continue
        stamp = (item.get("lastTimestamp") or item.get("eventTime")
                 or item.get("firstTimestamp"))
        if stamp:
            try:
                if parse_instant(stamp) < since:
                    continue
            except SystemExit:
                pass
        obj = item.get("involvedObject", {}).get("name", "?")
        found.append(f"{item['reason']} · {obj} · {stamp}")
    return found

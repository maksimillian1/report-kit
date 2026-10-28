"""What OpenCost publishes in Prometheus, read back over a window: every price
it held for a node, a volume, a load balancer and the control plane, the nodes
it never priced, and which of those lines a register's queries read."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import jsonl, prometheus
from .window import Window

NODES = "nodes"
VOLUMES = "volumes"
LOAD_BALANCERS = "load_balancers"
CONTROL_PLANE = "control_plane"

LINE_METRICS = {
    NODES: ("node_total_hourly_cost", "node_cpu_hourly_cost",
            "node_ram_hourly_cost", "node_gpu_hourly_cost"),
    VOLUMES: ("pv_hourly_cost",),
    LOAD_BALANCERS: ("kubecost_load_balancer_cost",),
    CONTROL_PLANE: ("kubecost_cluster_management_cost",),
}

# One series per item: OpenCost scraped by two jobs publishes every price twice.
LINE_QUERIES = {
    NODES: "max by (node, instance_type, region, provider_id) (node_total_hourly_cost)",
    VOLUMES: "max by (persistentvolume, provider_id) (pv_hourly_cost)",
    LOAD_BALANCERS: "max by (namespace, service_name) (kubecost_load_balancer_cost)",
    CONTROL_PLANE: "max by (provisioner_name) (kubecost_cluster_management_cost)",
}
ITEM_LABELS = {NODES: ("node",), VOLUMES: ("persistentvolume",),
               LOAD_BALANCERS: ("namespace", "service_name"),
               CONTROL_PLANE: ("provisioner_name",)}
SPOT_QUERY = "max by (node) (kubecost_node_is_spot)"
PRICE_STEP = "60s"          # OpenCost's own recommended scrape interval

METRIC_NAME = re.compile(r"[a-zA-Z_:][a-zA-Z0-9_:]*")


@dataclass(frozen=True)
class Price:
    """One value OpenCost published for one item, from `since` until it changed
    or the window ended. USD per hour; for a volume, per GiB-hour."""

    line: str
    item: str
    hourly: float
    since: datetime
    labels: dict = field(default_factory=dict)


def lines_read(queries) -> tuple[str, ...]:
    """The price lines whose OpenCost metrics any of `queries` names."""
    names = {name for query in queries for name in METRIC_NAME.findall(query)}
    return tuple(line for line, metrics in LINE_METRICS.items()
                 if names.intersection(metrics))


def published_prices(prom_url: str, window: Window, lines,
                     step: str = PRICE_STEP) -> list[Price]:
    spot = spot_nodes(prom_url, window, step) if NODES in lines else set()
    prices = []
    for line in lines:
        for series in prometheus.prom_query_range(prom_url, LINE_QUERIES[line],
                                                  window.start, window.end, step):
            labels = dict(series.get("metric") or {})
            if line == NODES:
                labels["spot"] = labels.get("node") in spot
            prices += price_changes(line, labels, series.get("values") or [])
    return prices


def price_changes(line: str, labels: dict, values: list) -> list[Price]:
    """A Price at the first sample and at every sample that differs from the
    one before it — a spot price moves, an on-demand one should not."""
    item = "/".join(labels.get(name, "?") for name in ITEM_LABELS[line])
    prices: list[Price] = []
    for stamp, hourly in jsonl.parse_values(values):
        if not prices or hourly != prices[-1].hourly:
            prices.append(Price(line, item, hourly, instant(stamp), labels))
    return prices


def spot_nodes(prom_url: str, window: Window, step: str = PRICE_STEP) -> set[str]:
    return {series["metric"].get("node", "")
            for series in prometheus.prom_query_range(prom_url, SPOT_QUERY,
                                                      window.start, window.end, step)
            if any(value == 1 for _, value in jsonl.parse_values(series["values"]))}


def unpriced_nodes(prom_url: str, window: Window) -> list[str]:
    """Nodes kube-state-metrics saw during the window that OpenCost never
    priced: a sum over node prices is short by each of them."""
    lookback = f"[{math.ceil(window.seconds)}s]"
    query = (f"max by (node) (max_over_time(kube_node_info{lookback})) unless on (node) "
             f"max by (node) (max_over_time(node_total_hourly_cost{lookback}))")
    return sorted(series["metric"].get("node", "?")
                  for series in prometheus.prom_query(prom_url, query, at=window.end))


def regions(prom_url: str, window: Window) -> set[str]:
    """The regions OpenCost's node prices name over the window."""
    query = (f"count by (region) "
             f"(max_over_time(node_total_hourly_cost[{math.ceil(window.seconds)}s]))")
    return {series["metric"].get("region", "")
            for series in prometheus.prom_query(prom_url, query, at=window.end)} - {""}


def instant(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, timezone.utc)

"""A value's `metric:` — the register ref that defines what it measures —
checked against the `metrics.yaml` of the execution it belongs to."""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from report_kit.register import REGISTER, RegisterError, read_register, register_above

from .registry import Registry

METRIC = re.compile(r"^(?:(?P<execution>[\w.-]+(?:/[\w.-]+)*)/)?(?P<ref>[MDRE][1-9]\d*)$")


def metric_of(spec: dict) -> str | None:
    """The register ref a value measures: its `metric:`, or the ref its
    `from:` works it out from."""
    if "metric" in spec:
        return str(spec["metric"])
    source = spec.get("from")
    if isinstance(source, dict) and "metric" in source:
        return str(source["metric"])
    return None


def letter_of(metric: str) -> str | None:
    match = METRIC.match(metric)
    return match["ref"][0] if match else None


class LinkProblem(NamedTuple):
    name: str
    metric: str
    why: str


def named_register(registry: Registry, execution: str) -> Path:
    """`00-baseline/M2` cites the baseline's register, from the report root or
    from its `executions/`."""
    for directory in (registry.root / execution, registry.root / "executions" / execution):
        if (directory / REGISTER).is_file():
            return directory / REGISTER
    raise LookupError(f"no {REGISTER} in {execution} or executions/{execution}")


def nearest_register(registry: Registry, spec: dict) -> Path:
    """A bare ref belongs to the execution whose data its `from:` reads: the
    first register above that file, no higher than the report root."""
    source = spec.get("from")
    file = source.get("file") if isinstance(source, dict) else None
    if not file:
        raise LookupError("a bare ref needs a from: to find its execution; "
                          "write <execution>/<ref> instead")
    start = (registry.root / str(file)).resolve().parent
    if registry.root not in (start, *start.parents):
        raise LookupError(f"{file} is outside the report")
    found = register_above(start, registry.root)
    if found is None:
        raise LookupError(f"no {REGISTER} between {file} and the report root")
    return found


def defined_refs(path: Path, cache: dict[Path, set[str]]) -> set[str]:
    if path not in cache:
        cache[path] = {metric.ref for metric in read_register(path).metrics}
    return cache[path]


def check_links(registry: Registry) -> tuple[int, list[LinkProblem]]:
    """How many entries name a metric, and each one whose ref its execution's
    register does not define."""
    cache: dict[Path, set[str]] = {}
    seen, problems = 0, []
    for name, spec in registry.entries.items():
        metric = metric_of(spec)
        if metric is None:
            continue
        seen += 1
        problem = link_problem(registry, spec, metric, cache)
        if problem:
            problems.append(LinkProblem(name, metric, problem))
    return seen, problems


def link_problem(registry: Registry, spec: dict, metric: str,
                 cache: dict[Path, set[str]]) -> str | None:
    match = METRIC.match(metric)
    if not match:
        return "not a ref such as M1 or 00-baseline/M1"
    source = spec.get("from")
    reads = source.get("metric") if isinstance(source, dict) else None
    if reads is not None and str(reads) != metric:
        return f"its from: works it out as {reads}"
    try:
        path = (named_register(registry, match["execution"]) if match["execution"]
                else nearest_register(registry, spec))
        refs = defined_refs(path, cache)
    except (LookupError, RegisterError) as exc:
        return str(exc)
    if match["ref"] not in refs:
        return f"{registry.relative(path)} defines no {match['ref']}"
    return None

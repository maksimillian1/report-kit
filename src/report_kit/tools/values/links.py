"""A value's `metric:` — the register ref that defines what it measures —
checked against the `metrics.yaml` of the execution it belongs to."""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from report_kit.register import REGISTER, RegisterError, read_register

from .registry import Registry

METRIC = re.compile(r"^(?:(?P<execution>[\w.-]+(?:/[\w.-]+)*)/)?(?P<ref>[MDRE][1-9]\d*)$")


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
    for directory in (start, *start.parents):
        if (directory / REGISTER).is_file():
            return directory / REGISTER
        if directory == registry.root:
            break
    raise LookupError(f"no {REGISTER} between {file} and the report root")


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
        if "metric" not in spec:
            continue
        seen += 1
        metric = str(spec["metric"])
        match = METRIC.match(metric)
        if not match:
            problems.append(LinkProblem(name, metric, "not a ref such as M1 or 00-baseline/M1"))
            continue
        try:
            path = (named_register(registry, match["execution"]) if match["execution"]
                    else nearest_register(registry, spec))
            refs = defined_refs(path, cache)
        except (LookupError, RegisterError) as exc:
            problems.append(LinkProblem(name, metric, str(exc)))
            continue
        if match["ref"] not in refs:
            problems.append(LinkProblem(
                name, metric, f"{registry.relative(path)} defines no {match['ref']}"))
    return seen, problems

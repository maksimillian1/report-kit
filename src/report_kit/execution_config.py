"""`execution.yaml`: how a point of this execution is run and judged — what it
is run with, when its window closes, and what makes the point valid.
`metrics.yaml` says what is read and from where; this file says how a point is
run, when it is over and whether it counts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from . import opencost
from .register import Register
from .strict_yaml import UniqueKeyLoader, unknown_keys
from .text import fill

EXECUTION = "execution.yaml"
WINDOW = "window_closes_when_back_to_idle"
GUARDS = "point_validity_guards"
POINT = "point"
PRICES = "prices_match_aws"
SECTIONS = (POINT, WINDOW, GUARDS, PRICES)

GUARD_REF = re.compile(r"^G([1-9]\d*)$")
SUBSTITUTION = re.compile(r"^\{[A-Za-z_]\w*\}$")
GUARD_KEYS = frozenset({"metric", "promql", "min", "max"})
IDLE_KEYS = frozenset({"idle_replicas", "max_replicas"})
POINT_KEYS = frozenset({"settings", "load", "hold_seconds", "freeze", "step", "guards_at"})
PRICE_KEYS = frozenset({"within"})
SETTING_KEYS = frozenset({"default"})
SETTING_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
LOADS = ("foreground", "background")
GUARD_INSTANTS = ("load_end", "window_end")
FREEZE_ENTRY = re.compile(r"^[A-Za-z]+/\S+$")
STEP = re.compile(r"^\d+(ms|s|m|h)$")


class ExecutionError(Exception):
    """Anything an execution.yaml makes impossible to run."""


@dataclass(frozen=True)
class IdleTarget:
    """A deployment the load scales: the window closes once it is back at
    `idle_replicas` and has stayed there, and reaching `max_replicas` means the
    point measured that limit rather than the system."""

    deployment: str
    idle_replicas: int
    max_replicas: int | None = None


@dataclass(frozen=True)
class Guard:
    """One check a point must pass to be compared with the others. `metric`
    names the register ref whose query it reuses; `promql` is that query."""

    ref: str
    promql: str
    min: str | None = None
    max: str | None = None
    metric: str | None = None


@dataclass(frozen=True)
class PriceMatch:
    """Every price OpenCost published during the window is held against AWS's
    for the same thing, and one further off than `within` — a share of AWS's
    price — puts the point in doubt."""

    within: float


@dataclass(frozen=True)
class Setting:
    """What a point is run with: a `--name` flag on the runner, filled into
    the load command and the guards, and recorded under `settings`."""

    name: str
    default: str | None = None


@dataclass(frozen=True)
class PointPlan:
    """How a point is run. A runner holds its profile's defaults; what
    `execution.yaml` names under `point:` replaces them key by key."""

    settings: tuple[Setting, ...] = ()
    load: str = "foreground"
    hold_seconds: float = 60.0
    freeze: tuple[str, ...] = ()
    step: str = "15s"
    guards_at: str = "load_end"


@dataclass(frozen=True)
class Execution:
    path: Path
    window_closes_when_back_to_idle: tuple[IdleTarget, ...] = ()
    point_validity_guards: tuple[Guard, ...] = ()
    point: dict | None = None
    prices_match_aws: PriceMatch | None = None

    def plan(self, defaults: PointPlan) -> PointPlan:
        return replace(defaults, **(self.point or {}))


def read_execution(path: Path, register: Register) -> Execution:
    """`register` is the execution's metrics.yaml, which a guard's `metric:`
    is looked up in."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ExecutionError(f"cannot read {path}: {exc.strerror}") from None
    return parse_execution(text, path, register)


def parse_execution(text: str, path: Path, register: Register) -> Execution:
    try:
        doc = yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ExecutionError(f"{path}: {exc}") from None
    if doc is None:
        return Execution(path)
    if not isinstance(doc, dict):
        raise ExecutionError(f"{path}: expected a mapping with {' and '.join(SECTIONS)}")
    unknown = unknown_keys(doc, frozenset(SECTIONS))
    if unknown:
        raise ExecutionError(f"{path}: unknown section {unknown[0]!r} — this file "
                             f"holds {' and '.join(SECTIONS)}")
    idle = tuple(idle_target_of(name, spec) for name, spec in entries(doc, WINDOW, path))
    guards = tuple(guard_of(ref, spec, register) for ref, spec in entries(doc, GUARDS, path))
    check_guard_order(guards, path)
    return Execution(path, idle, guards, point_of(doc.get(POINT), path),
                     price_match_of(doc.get(PRICES), path, register))


def point_of(raw: object, path: Path) -> dict:
    """The `point:` keys this execution sets, each checked; the rest stay the
    runner's."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ExecutionError(f"{path}: {POINT} must be a mapping")
    refuse_unknown_keys(POINT, raw, POINT_KEYS)
    readers = {"settings": settings_of, "load": load_of, "hold_seconds": hold_of,
               "freeze": freeze_of, "step": step_of, "guards_at": guards_at_of}
    return {key: readers[key](raw[key]) for key in raw}


def price_match_of(raw: object, path: Path, register: Register) -> PriceMatch | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ExecutionError(f"{path}: {PRICES} must be a mapping, such as {{within: 0.01}}")
    refuse_unknown_keys(PRICES, raw, PRICE_KEYS)
    within = raw.get("within")
    if isinstance(within, bool) or not isinstance(within, (int, float)) \
            or not 0 < within < 1:
        raise ExecutionError(f"{PRICES}.within is how far apart two prices may be, "
                             f"as a share of AWS's, between 0 and 1 — not {within!r}")
    if not opencost.lines_read(metric.promql for metric in register.exported):
        raise ExecutionError(f"{path}: {PRICES} is set, but no query in "
                             f"{register.path.name} reads a price OpenCost publishes")
    return PriceMatch(float(within))


def settings_of(raw: object) -> tuple[Setting, ...]:
    if not isinstance(raw, dict) or not raw:
        raise ExecutionError(f"{POINT}.settings must name at least one setting")
    settings = []
    for name, spec in raw.items():
        if not SETTING_NAME.match(str(name)):
            raise ExecutionError(f"setting {name!r}: lowercase letters, digits and _")
        spec = spec or {}
        if not isinstance(spec, dict):
            raise ExecutionError(f"setting {name}: a mapping, such as {{default: 10m}}")
        refuse_unknown_keys(f"setting {name}", spec, SETTING_KEYS)
        default = spec.get("default")
        settings.append(Setting(str(name), None if default is None else str(default)))
    return tuple(settings)


def load_of(raw: object) -> str:
    if raw not in LOADS:
        raise ExecutionError(f"{POINT}.load is {raw!r}, not one of {', '.join(LOADS)}")
    return raw


def hold_of(raw: object) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw <= 0:
        raise ExecutionError(f"{POINT}.hold_seconds must be a positive number of seconds")
    return float(raw)


def freeze_of(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(
            isinstance(entry, str) and FREEZE_ENTRY.match(entry) for entry in raw):
        raise ExecutionError(f"{POINT}.freeze is a list of kind/name, such as deployment/api")
    return tuple(raw)


def step_of(raw: object) -> str:
    if not isinstance(raw, str) or not STEP.match(raw):
        raise ExecutionError(f"{POINT}.step is a Prometheus resolution, such as 15s")
    return raw


def guards_at_of(raw: object) -> str:
    if raw not in GUARD_INSTANTS:
        raise ExecutionError(f"{POINT}.guards_at is {raw!r}, not one of "
                             f"{', '.join(GUARD_INSTANTS)}")
    return raw


def entries(doc: dict, name: str, path: Path) -> list[tuple[str, dict]]:
    found = doc.get(name)
    if found is None:
        return []
    if not isinstance(found, dict) or not all(isinstance(spec, dict)
                                              for spec in found.values()):
        raise ExecutionError(f"{path}: {name} must be a mapping of name to entry")
    return [(str(key), spec) for key, spec in found.items()]


def idle_target_of(deployment: str, spec: dict) -> IdleTarget:
    refuse_unknown_keys(deployment, spec, IDLE_KEYS)
    idle = replica_count(deployment, "idle_replicas", spec.get("idle_replicas"))
    if spec.get("max_replicas") is None:
        return IdleTarget(deployment, idle)
    most = replica_count(deployment, "max_replicas", spec["max_replicas"])
    if most <= idle:
        raise ExecutionError(f"{deployment}: max_replicas {most} is not above "
                             f"idle_replicas {idle}")
    return IdleTarget(deployment, idle, most)


def replica_count(deployment: str, key: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ExecutionError(f"{deployment}: {key} must be a whole number of "
                             f"replicas, not {value!r}")
    return value


def guard_of(ref: str, spec: dict, register: Register) -> Guard:
    if not GUARD_REF.match(ref):
        raise ExecutionError(f"guard {ref!r} is not G followed by a number")
    refuse_unknown_keys(ref, spec, GUARD_KEYS)
    if ("metric" in spec) == ("promql" in spec):
        raise ExecutionError(f"{ref}: give exactly one of metric (a register ref "
                             f"whose query it reuses) and promql (its own query)")
    bounds = {key: bound_of(ref, key, spec[key]) for key in ("min", "max") if key in spec}
    if not bounds:
        raise ExecutionError(f"{ref}: a guard needs min, max or both")
    if "promql" in spec:
        return Guard(ref, one_line(ref, spec["promql"]), **bounds)
    metric = str(spec["metric"])
    exported = {m.ref: m.promql for m in register.exported}
    if metric not in exported:
        raise ExecutionError(f"{ref}: metric {metric} is not an M ref with a promql "
                             f"in {register.path.name}")
    return Guard(ref, exported[metric], metric=metric, **bounds)


def bound_of(ref: str, key: str, value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ExecutionError(f"{ref}: {key} must be a number or a {{name}} substitution")
    text = str(value).strip()
    if isinstance(value, str) and not SUBSTITUTION.match(text):
        try:
            float(text)
        except ValueError:
            raise ExecutionError(f"{ref}: {key} {text!r} is neither a number nor a "
                                 f"{{name}} substitution") from None
    return text


def one_line(ref: str, value: object) -> str:
    if not isinstance(value, str) or "\n" in value.strip():
        raise ExecutionError(f"{ref}: promql must be one line of text")
    return value.strip()


def refuse_unknown_keys(name: str, spec: dict, allowed: frozenset[str]) -> None:
    unknown = unknown_keys(spec, allowed)
    if unknown:
        raise ExecutionError(f"{name}: unknown key {unknown[0]!r} — expected "
                             f"{', '.join(sorted(allowed))}")


def check_guard_order(guards: tuple[Guard, ...], path: Path) -> None:
    previous = 0
    for guard in guards:
        number = int(GUARD_REF.match(guard.ref).group(1))
        if number <= previous:
            raise ExecutionError(f"{path}: {guard.ref} is out of order")
        previous = number


def run_guards(execution: Execution, substitutions: dict) -> list[dict]:
    """The guards as `prometheus.evaluate_guards` takes them, every `{name}`
    in a bound or a query filled from the run's own arguments."""
    guards = []
    for guard in execution.point_validity_guards:
        entry: dict = {"ref": guard.ref,
                       "query": filled(guard.ref, guard.promql, substitutions)}
        for key, bound in (("min", guard.min), ("max", guard.max)):
            if bound is None:
                continue
            text = filled(guard.ref, bound, substitutions)
            try:
                entry[key] = float(text)
            except ValueError:
                raise ExecutionError(f"{guard.ref}: {key} is {text!r} once filled, "
                                     f"not a number") from None
        guards.append(entry)
    return guards


def filled(ref: str, text: str, substitutions: dict) -> str:
    try:
        return fill(text, {key: str(value) for key, value in substitutions.items()})
    except KeyError as exc:
        raise ExecutionError(f"{ref} names {{{exc.args[0]}}}, which this run does "
                             f"not fill — it fills {', '.join(sorted(substitutions))}"
                             ) from None

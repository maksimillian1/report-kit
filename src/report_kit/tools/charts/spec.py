"""`charts/charts.yaml`: which shape each CSV is drawn as, and what goes on it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .errors import ChartError
from .kinds import KINDS, MARKED, Marks

CHART_DIR = Path("charts")
SPEC = CHART_DIR / "charts.yaml"
KEYS = ("kind", "rule", "mark_x", "points")
MARK_KEYS = ("at", "text")


@dataclass(frozen=True)
class Entry:
    path: Path
    kind: str
    marks: Marks

    @property
    def name(self) -> str:
        return self.path.stem


class StrictLoader(yaml.SafeLoader):
    pass


def no_duplicates(loader, node, deep=False):
    """PyYAML keeps the last of two equal keys; a chart given twice is a mistake."""
    keys = [loader.construct_object(key, deep=deep) for key, _ in node.value]
    twice = sorted({str(key) for key in keys if keys.count(key) > 1})
    if twice:
        raise ChartError(f"{SPEC}: {', '.join(twice)} given twice")
    return loader.construct_mapping(node, deep)


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                             no_duplicates)


def checked(kind: str, marks: Marks) -> Marks:
    if marks != Marks() and kind not in MARKED:
        raise ChartError(f"rule, mark_x and points draw on "
                         f"{', '.join(MARKED)} only, not {kind}")
    return marks


def mark(name: str, key: str, given):
    if given is None:
        return None
    if (not isinstance(given, dict) or "at" not in given
            or set(given) - set(MARK_KEYS)):
        raise ChartError(f"{SPEC}: {name}: {key} wants "
                         f"{{at: <number>, text: <words>}}")
    at = given["at"]
    if isinstance(at, bool) or not isinstance(at, (int, float)):
        raise ChartError(f"{SPEC}: {name}: {key}.at must be a number, "
                         f"got {at!r}")
    return float(at), str(given.get("text", ""))


def entry(name: str, given) -> Entry:
    if not isinstance(given, dict):
        raise ChartError(f"{SPEC}: {name}: expected `kind:` and its options "
                         f"under the name")
    unknown = sorted(set(given) - set(KEYS))
    if unknown:
        raise ChartError(f"{SPEC}: {name}: unknown key {', '.join(unknown)} — "
                         f"have {', '.join(KEYS)}")
    kind = given.get("kind")
    if kind not in KINDS:
        raise ChartError(f"{SPEC}: {name}: kind must be one of "
                         f"{', '.join(KINDS)}, got {kind!r}")
    points = given.get("points", False)
    if not isinstance(points, bool):
        raise ChartError(f"{SPEC}: {name}: points is true or false, "
                         f"got {points!r}")
    marks = Marks(rule=mark(name, "rule", given.get("rule")),
                  mark_x=mark(name, "mark_x", given.get("mark_x")),
                  join=not points)
    try:
        checked(kind, marks)
    except ChartError as exc:
        raise ChartError(f"{SPEC}: {name}: {exc}") from exc
    return Entry(CHART_DIR / f"{name}.csv", kind, marks)


def read_spec() -> list[Entry]:
    if not SPEC.exists():
        raise ChartError(f"{SPEC} not found: --all and --check read it")
    try:
        given = yaml.load(SPEC.read_text(encoding="utf-8"), Loader=StrictLoader)
    except yaml.YAMLError as exc:
        raise ChartError(f"{SPEC}: {exc}") from exc
    if not isinstance(given, dict) or not given:
        raise ChartError(f"{SPEC} names no chart")
    return [entry(str(name), spec) for name, spec in given.items()]

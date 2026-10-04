"""`charts/charts.yaml`: which shape each CSV is drawn as, what goes on it, and in which themes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .canvas import DEFAULT_THEMES, RAMP_STEPS, THEME_KEYS, svg_name
from .errors import ChartError
from .kinds import KINDS, MARKED, Marks

CHART_DIR = Path("charts")
SPEC = CHART_DIR / "charts.yaml"
THEMES = "themes"
KEYS = ("kind", "rule", "mark_x", "points", "themes")
MARK_KEYS = ("at", "text")


@dataclass(frozen=True)
class Entry:
    path: Path
    kind: str
    marks: Marks
    themes: tuple = ()

    @property
    def name(self) -> str:
        return self.path.stem


@dataclass(frozen=True)
class Spec:
    entries: tuple
    themes: dict

    def pairs(self) -> list:
        """(entry, theme name, colours) for every SVG the spec draws."""
        return [(entry, name, colours) for entry in self.entries
                for name, colours in self.themes.items()
                if not entry.themes or name in entry.themes]

    def svgs(self) -> set:
        return {svg_name(entry.name, name) for entry, name, _ in self.pairs()}


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
    return Entry(CHART_DIR / f"{name}.csv", kind, marks,
                 chart_themes(name, given.get("themes")))


def chart_themes(name: str, given) -> tuple:
    if given is None:
        return ()
    if (not isinstance(given, list) or not given
            or not all(isinstance(theme_name, str) for theme_name in given)):
        raise ChartError(f"{SPEC}: {name}: themes is a list of theme names, "
                         f"e.g. [light]")
    return tuple(given)


def defined(entries, known: dict) -> None:
    for chart in entries:
        unknown = [theme_name for theme_name in chart.themes if theme_name not in known]
        if unknown:
            raise ChartError(f"{SPEC}: {chart.name}: themes names "
                             f"{', '.join(unknown)}, which the spec does not "
                             f"define — have {', '.join(known)}")


def theme(name: str, given) -> dict:
    if given is not None and not isinstance(given, dict):
        raise ChartError(f"{SPEC}: themes.{name}: expected colours under the "
                         f"name, or {{}} for the built-in one")
    unknown = sorted(set(given or {}) - set(THEME_KEYS))
    if unknown:
        raise ChartError(f"{SPEC}: themes.{name}: unknown key "
                         f"{', '.join(unknown)} — have {', '.join(THEME_KEYS)}")
    merged = {**DEFAULT_THEMES.get(name, {}), **(given or {})}
    missing = [key for key in THEME_KEYS if key not in merged]
    if missing:
        raise ChartError(f"{SPEC}: themes.{name} is not built in, so it needs "
                         f"{', '.join(missing)}")
    if not isinstance(merged["ramp"], list) or len(merged["ramp"]) != RAMP_STEPS:
        raise ChartError(f"{SPEC}: themes.{name}.ramp needs {RAMP_STEPS} colours")
    return merged


def themes(given) -> dict:
    if given is None:
        return {name: dict(colours) for name, colours in DEFAULT_THEMES.items()}
    if not isinstance(given, dict) or not given:
        raise ChartError(f"{SPEC}: themes lists at least one theme by name, "
                         f"e.g. `light: {{}}`")
    return {str(name): theme(str(name), colours) for name, colours in given.items()}


def load() -> dict:
    try:
        given = yaml.load(SPEC.read_text(encoding="utf-8"), Loader=StrictLoader)
    except yaml.YAMLError as exc:
        raise ChartError(f"{SPEC}: {exc}") from exc
    if not isinstance(given, dict):
        raise ChartError(f"{SPEC} names no chart")
    return given


def read_spec() -> Spec:
    if not SPEC.exists():
        raise ChartError(f"{SPEC} not found: --all and --check read it")
    given = load()
    charts = {str(name): spec for name, spec in given.items() if name != THEMES}
    if not charts:
        raise ChartError(f"{SPEC} names no chart")
    entries = tuple(entry(name, spec) for name, spec in charts.items())
    known = themes(given.get(THEMES))
    defined(entries, known)
    return Spec(entries, known)


def available_themes() -> dict:
    """For one file drawn by hand: every built-in, with charts.yaml's themes over them."""
    built_in = themes(None)
    if not SPEC.exists():
        return built_in
    return {**built_in, **themes(load().get(THEMES) or None)}

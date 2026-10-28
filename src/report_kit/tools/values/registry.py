"""A loaded `report-values.yaml`: its values, their arithmetic, and where the file is."""

from __future__ import annotations

import ast
import os
import pathlib
import re
from dataclasses import dataclass

import yaml

from report_kit import arith
from report_kit.strict_yaml import UniqueKeyLoader

from .errors import RegistryError
from .corpus import Document, read_document, relative


REGISTRY = "report-values.yaml"
KINDS = ("M", "R", "D", "E")
MARK = {"M": "", "R": "ᴿ", "D": "ᴰ", "E": "ᴱ"}
DEFAULT_GROUP = "inputs"
DEFAULT_DECIMALS = 2
HOURS_DECIMALS = 0


# No zero padding and no V?0: the tool writes VD7, and `renumber` would
# rewrite a hand-typed VD07 into it — silently orphaning every mark in
# every document that points at the padded form. Caught here instead.
REF_RE = re.compile(r"^V([MRDE])([1-9]\d*)$")


class Pending:
    """A value whose value does not exist yet.

    A singleton, and compared with `is` everywhere, so copying and pickling
    have to return the same object or a round-trip would produce a value that
    is pending and does not look it.
    """

    _instance: Pending | None = None

    def __new__(cls) -> Pending:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "pending"

    def __copy__(self) -> Pending:
        return self

    def __deepcopy__(self, memo: dict) -> Pending:
        return self

    def __reduce__(self) -> str:
        return "PENDING"


PENDING = Pending()
Value = float | Pending


def find_registry(explicit: str | os.PathLike | None = None,
                  start: str | os.PathLike | None = None,
                  ) -> tuple[pathlib.Path, pathlib.Path]:
    """The report root and the registry file inside it. The root is whatever
    directory holds `report-values.yaml`, because every `scan` entry and every
    `appears_in` path is relative to it."""
    if explicit:
        path = pathlib.Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise RegistryError(f"no such registry: {path}")
        if path.name == "figures.yaml":
            raise RegistryError(f"{path} is the registry's name before 0.4 — run "
                                f"report-kit values migrate --path {path}")
        return path.parent, path
    here = pathlib.Path(start or pathlib.Path.cwd()).expanduser().resolve()
    for folder in [here, *here.parents]:
        candidate = folder / REGISTRY
        if candidate.is_file():
            return folder, candidate
    for folder in [here, *here.parents]:
        if (folder / "figures.yaml").is_file():
            raise RegistryError(f"{folder / 'figures.yaml'} is the registry's name "
                                f"before 0.4 — run report-kit values migrate")
    raise RegistryError(f"no {REGISTRY} in {here} or any parent — run this inside "
                        f"a report, or name one with --path")


def parse_registry(text: str, path: pathlib.Path) -> dict:
    try:
        doc = yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise RegistryError(f"{path} is not valid YAML: "
                          f"{str(exc).splitlines()[0]}") from exc
    if doc is None:
        raise RegistryError(f"{path} is empty")
    if not isinstance(doc, dict):
        raise RegistryError(f"{path} must be a mapping, not a "
                          f"{type(doc).__name__}")
    return doc


def entries_of(doc: dict, path: pathlib.Path) -> dict[str, dict]:
    if "values" not in doc:
        raise RegistryError(f"{path} has no 'values' mapping")
    entries = doc["values"]
    if entries is None:
        raise RegistryError(f"{path} has an empty 'values' mapping")
    if not isinstance(entries, dict):
        raise RegistryError(f"{path}: 'values' must be a mapping of name to "
                          f"value, not a {type(entries).__name__}")
    bad = [k for k in entries if not isinstance(k, str)]
    if bad:
        raise RegistryError(f"{path}: value names must be strings; found "
                          f"{bad[0]!r}")
    return {name: (spec if isinstance(spec, dict) else {})
            for name, spec in entries.items()}


def sequence_of(doc: dict, key: str, path: pathlib.Path) -> tuple:
    value = doc.get(key) or []
    if not isinstance(value, list):
        raise RegistryError(f"{path}: '{key}' must be a list, not a "
                          f"{type(value).__name__}")
    return tuple(value)


@dataclass(frozen=True)
class Registry:
    """A loaded `report-values.yaml`, and everything derived from it.

    Constructed straight from a mapping for tests and for callers that build a
    registry in memory; `load()` is the file path in. `root` is what every
    relative path in the file is relative to, which is the directory the file
    itself sits in.
    """

    entries: dict[str, dict]
    root: pathlib.Path = pathlib.Path(".")
    path: pathlib.Path | None = None
    scan: tuple = ()
    allow: tuple = ()
    retired: tuple = ()
    points: object = None

    def __post_init__(self) -> None:
        # Resolved once, here, because every path the checks report is
        # `relative_to` this one. A root left as given — a relative path, or
        # anything under a symlinked directory, which on macOS is every
        # temporary directory — makes `relative_to` fail and each file is
        # then named by a chain of `..`, which `allow` entries and
        # `appears_in` paths no longer match.
        object.__setattr__(self, "root", pathlib.Path(self.root).resolve())

    @classmethod
    def load(cls, explicit: str | os.PathLike | None = None,
             start: str | os.PathLike | None = None) -> Registry:
        root, path = find_registry(explicit, start)
        doc = parse_registry(path.read_text(), path)
        return cls(entries=entries_of(doc, path), root=root, path=path,
                   scan=sequence_of(doc, "scan", path),
                   allow=sequence_of(doc, "allow", path),
                   retired=sequence_of(doc, "retired", path),
                   points=doc.get("points"))

    # -- entries ----------------------------------------------------------

    def spec(self, name: str) -> dict:
        if name not in self.entries:
            raise RegistryError(f"unknown value '{name}'")
        return self.entries[name]

    def resolve(self) -> dict[str, Value]:
        """Every value's number, formulas included, in file order."""
        resolved: dict[str, Value] = {}
        for name in self.entries:
            _resolve_one(name, self.entries, resolved, [])
        return resolved

    def value(self, name: str) -> float:
        """One value's number, for a caller that needs it now."""
        self.spec(name)
        value = _resolve_one(name, self.entries, {}, [])
        if value is PENDING:
            raise RegistryError(f"value '{name}' is pending, and a number is "
                              f"needed here")
        return value

    def inputs(self, name: str) -> list[str]:
        """The values a formula names, in the order it names them."""
        spec = self.spec(name)
        if "formula" not in spec:
            return []
        return arith.names(_formula(name, spec["formula"]))

    def effective_kind(self, name: str, _seen: tuple[str, ...] = ()) -> str:
        """The kind a value prints as: the weakest input decides, so a
        derived value with an estimate anywhere upstream prints ᴱ."""
        kind = self.spec(name).get("kind", "?")
        if kind != "D":
            return kind
        for source in self.inputs(name):
            if source in self.entries and source not in _seen:
                if self.effective_kind(source, _seen + (name,)) == "E":
                    return "E"
        return kind

    def by_ref(self) -> dict[str, str]:
        """Ref to the name of its value. One with no ref is simply not in here;
        `validate` is what complains about it."""
        index = {}
        for name, spec in self.entries.items():
            ref = spec.get("ref")
            if ref is not None:
                index.setdefault(str(ref), name)
        return index

    def display(self, name: str, value: Value) -> str:
        """The value written out at its own precision."""
        if value is PENDING:
            return "pending"
        spec = self.entries.get(name) or {}
        default = (HOURS_DECIMALS if str(spec.get("unit", "")) == "hours"
                   else DEFAULT_DECIMALS)
        decimals = spec.get("display", default)
        if isinstance(decimals, bool) or not isinstance(decimals, int) \
                or decimals < 0:
            raise RegistryError(f"value '{name}': display must be a whole "
                              f"number of decimals, not {decimals!r}")
        return f"{value:,.{decimals}f}"

    def groups(self) -> dict[str, list[str]]:
        """Values by group, in the order the file puts them: a fixed list
        here would bake one report's subjects into a general tool."""
        grouped: dict[str, list[str]] = {}
        for name, spec in self.entries.items():
            grouped.setdefault(str(spec.get("group", DEFAULT_GROUP)),
                               []).append(name)
        return grouped

    # -- documents --------------------------------------------------------

    def documents(self) -> list[Document]:
        """Every file `scan` names, each read once. Entries overlap freely,
        and a file counted twice would double the marked-number count, which
        is the one number that notices a ref orphaned by a delete."""
        seen, docs = set(), []
        for entry in self.scan:
            for path in self._match(str(entry)):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                docs.append(read_document(path, self.root))
        return docs

    def _match(self, entry: str) -> list[pathlib.Path]:
        direct = (self.root / entry).resolve()
        if direct.is_file():
            return [direct]
        try:
            return [p for p in sorted(self.root.glob(entry)) if p.is_file()]
        except (ValueError, IndexError) as exc:
            raise RegistryError(f"scan entry {entry!r} is not a usable path or "
                              f"glob: {exc}") from exc

    def document(self, rel: str) -> Document | None:
        """One document by its path relative to the root, or None if absent."""
        path = self.root / rel
        return read_document(path, self.root) if path.is_file() else None

    def relative(self, path: pathlib.Path) -> str:
        return relative(path, self.root)


def _formula(name: str, formula: object) -> ast.Expression:
    try:
        return arith.parse(formula)
    except arith.ArithError as exc:
        raise RegistryError(f"value '{name}': {exc}") from exc


def _eval(tree: ast.Expression, entries: dict[str, dict],
          resolved: dict[str, Value], stack: list[str]) -> Value:
    try:
        return arith.evaluate(
            tree, lambda name: _resolve_one(name, entries, resolved, stack))
    except arith.ArithError as exc:
        raise RegistryError(str(exc)) from exc


def _resolve_one(name: str, entries: dict[str, dict],
                 resolved: dict[str, Value], stack: list[str]) -> Value:
    if name in resolved:
        return resolved[name]
    if name not in entries:
        raise RegistryError(f"unknown value '{name}'")
    if name in stack:
        raise RegistryError("cycle: " + " -> ".join(stack + [name]))
    spec = entries[name]
    if spec.get("pending"):
        resolved[name] = PENDING
        return PENDING
    if "value" in spec:
        raw = spec["value"]
        try:
            value: Value = float(raw)
        except (TypeError, ValueError) as exc:
            raise RegistryError(f"'{name}': value {raw!r} is not a "
                              f"number") from exc
    elif "formula" in spec:
        value = _eval(_formula(name, spec["formula"]), entries, resolved,
                      stack + [name])
    elif "from" in spec:
        raise RegistryError(f"value '{name}' has a from: but no value yet — run "
                          f"`report-kit values pull {name}`")
    else:
        raise RegistryError(f"value '{name}' has neither value nor formula")
    resolved[name] = value
    return value


def stored_number(raw: object) -> float | None:
    if isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None

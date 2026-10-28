"""Values read back out of a run's data files: `pull`, and the evidence check."""

from __future__ import annotations

from typing import Iterable, NamedTuple

from . import evidence
from .errors import RegistryError
from .registry import Registry, stored_number
from .surgery import rewrite_values, value_text


def evidence_source(spec: dict) -> evidence.Source:
    if "formula" in spec:
        raise evidence.EvidenceError("from: and formula: together — a value "
                                     "is read from data or computed, not both")
    return evidence.read_source(spec["from"])


def reading(registry: Registry, name: str) -> float:
    """What the data files say a value should read. Raises
    `evidence.EvidenceError`, `MissingEvidence` when the file is absent."""
    return evidence.reproduce(evidence_source(registry.spec(name)),
                              registry.root)


class EvidenceRow(NamedTuple):
    name: str
    status: str
    stored: object
    found: float | None
    why: str = ""


def check_evidence(registry: Registry) -> list[EvidenceRow]:
    """Every value with a `from:`, its stored value against what its data
    reproduces at full precision."""
    rows = []
    for name, spec in registry.entries.items():
        if "from" not in spec:
            continue
        stored = spec.get("value")
        try:
            found = reading(registry, name)
        except evidence.MissingEvidence as exc:
            rows.append(EvidenceRow(name, "NO FILE", stored, None, str(exc)))
            continue
        except evidence.EvidenceError as exc:
            rows.append(EvidenceRow(name, "FAIL", stored, None, str(exc)))
            continue
        number = stored_number(stored)
        if number is None:
            status = "NO VALUE"
        else:
            status = "ok" if evidence.agrees(number, found) else "DIFFERS"
        rows.append(EvidenceRow(name, status, stored, found))
    return rows


class Pulled(NamedTuple):
    name: str
    old: object
    new: float


def pull_targets(registry: Registry, wanted: Iterable[str]) -> list[str]:
    wanted = list(wanted)
    if not wanted:
        return [name for name, spec in registry.entries.items()
                if "from" in spec]
    index = registry.by_ref()
    names = [index.get(item, item) for item in wanted]
    for name in names:
        if "from" not in registry.spec(name):
            raise RegistryError(f"value '{name}' has no from: to pull")
    return names


def pull(registry: Registry, wanted: Iterable[str] = ()
         ) -> tuple[list[Pulled], list[tuple[str, str]]]:
    """Fill each `value:` from what its `from:` reproduces. Returns what
    changed, and the entries with no reading — a gap is reported and its
    value left alone, never written as a zero."""
    if registry.path is None:
        raise RegistryError("pull rewrites a registry file; this one has none")
    changed, unread = [], []
    for name in pull_targets(registry, wanted):
        try:
            found = reading(registry, name)
        except evidence.EvidenceError as exc:
            unread.append((name, str(exc)))
            continue
        old = registry.entries[name].get("value")
        stored = stored_number(old)
        if stored is None or not evidence.agrees(stored, found):
            changed.append(Pulled(name, old, found))
    if changed:
        rewrite_values(registry.path,
                       {item.name: value_text(item.new) for item in changed})
    return changed, unread

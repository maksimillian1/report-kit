"""One value followed from every document that prints it, through the registry,
to the register ref that defines it and the run data that produce it."""

from __future__ import annotations

from dataclasses import dataclass

from report_kit import derive
from report_kit.register import RegisterError, read_register

from . import evidence
from .corpus import MARKED, Document
from .links import METRIC, metric_of, named_register, nearest_register
from .registry import MARK, Registry, Value


@dataclass(frozen=True)
class Step:
    text: str
    children: tuple[Step, ...] = ()


def trace(registry: Registry, values: dict[str, Value], name: str) -> Step:
    """`name` is a value's name or its ref."""
    name = registry.by_ref().get(name, name)
    spec = registry.spec(name)
    marks = marked_in(registry.documents(), str(spec.get("ref", "")))
    shown = Step("printed in " + (", ".join(marks) if marks else "no scanned document"))
    return Step(heading(registry, values, name), (shown, *definition(registry, values, name)))


def heading(registry: Registry, values: dict[str, Value], name: str) -> str:
    spec = registry.entries[name]
    kind = registry.effective_kind(name)
    unit = f" {spec['unit']}" if spec.get("unit") else ""
    return (f"{spec.get('ref', '?')} {name} = {registry.display(name, values[name])}"
            f"{MARK.get(kind, '')}{unit}")


def marked_in(documents: list[Document], ref: str) -> list[str]:
    """Each place a document prints the value, with the digits it prints."""
    found = []
    for document in documents:
        for line in document.lines:
            for match in MARKED.finditer(line.text):
                if ref in (match.group(2), match.group(4)):
                    shown = match.group(1) or match.group(3)
                    found.append(f"{document.rel}:{line.number} ({shown})")
    return found


def definition(registry: Registry, values: dict[str, Value], name: str) -> tuple[Step, ...]:
    spec = registry.entries[name]
    if spec.get("pending"):
        return (Step("pending — no number yet"),)
    if "formula" in spec:
        inputs = tuple(Step(heading(registry, values, used),
                            definition(registry, values, used))
                       for used in dict.fromkeys(registry.inputs(name)))
        return (Step(f"formula {spec['formula']}", inputs),)
    steps = [read_from(registry, spec)] if "from" in spec else []
    metric = metric_of(spec)
    reads_metric = isinstance(spec.get("from"), dict) and "metric" in spec["from"]
    if metric is not None and not reads_metric:
        steps.append(measures(registry, spec, metric))
    return tuple(steps) or (Step(f"source: {spec.get('source', 'none given')}"),)


def read_from(registry: Registry, spec: dict) -> Step:
    try:
        source = evidence.read_source(spec["from"])
    except evidence.EvidenceError as exc:
        return Step(f"from: cannot be read — {exc}")
    scale = f", × {source.scale:g}" if source.scale != 1 else ""
    if isinstance(source, evidence.PointSource):
        return Step(f"read from {source.file} at {source.path}{scale}")
    if isinstance(source, evidence.ExportSource):
        return Step(f"reduced from {source.file}: {source.reduce} of "
                    f"{evidence.describe(source)}{scale}")
    return worked_out(registry, spec, source, scale)


def worked_out(registry: Registry, spec: dict, source: evidence.MetricSource,
               scale: str) -> Step:
    path = registry.root / source.file
    try:
        register_path = nearest_register(registry, spec)
        register = read_register(register_path)
        steps = derive.explain(register, source.metric, path, source.file)
    except (LookupError, RegisterError, derive.DeriveError) as exc:
        return Step(f"{source.metric} of {source.file}: cannot be worked out — {exc}")
    what = register.by_ref[source.metric].what
    return Step(f"{source.metric} ({what}) of {source.file}, as "
                f"{registry.relative(register_path)} defines it{scale}",
                (derivation(steps),))


def derivation(steps: derive.Derivation) -> Step:
    return Step(f"{steps.name} = {steps.value:.6g}  ← {steps.how}",
                tuple(derivation(step) for step in steps.inputs))


def measures(registry: Registry, spec: dict, metric: str) -> Step:
    match = METRIC.match(metric)
    try:
        path = (named_register(registry, match["execution"])
                if match and match["execution"] else nearest_register(registry, spec))
        defined = read_register(path).by_ref.get(match["ref"] if match else metric)
    except (LookupError, RegisterError) as exc:
        return Step(f"measures {metric} — {exc}")
    if defined is None:
        return Step(f"measures {metric}, which {registry.relative(path)} does not define")
    return Step(f"measures {metric} ({defined.what}), as {registry.relative(path)} "
                f"defines it")


def lines(step: Step, depth: int = 0) -> list[str]:
    """The trace as indented text, one step per line."""
    marker = "" if depth == 0 else "  " * (depth - 1) + "└ "
    return [marker + step.text] + [line for child in step.children
                                   for line in lines(child, depth + 1)]


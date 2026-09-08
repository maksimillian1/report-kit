from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import shell
from .constants import ARROW, BAD, OK, WARN, die
from .clock import rfc3339, utcnow
from .window import Window


def prom_query(prom_url: str, query: str, at: datetime | None = None) -> list[dict]:
    """`at`, when given, evaluates the query as of that instant rather than
    Prometheus's own "now" — needed for anything checked well after the moment
    it actually describes (see check_guards)."""
    params: dict = {"query": query}
    if at is not None:
        params["time"] = at.timestamp()
    url = f"{prom_url}/api/v1/query?" + urllib.parse.urlencode(params)
    data = shell.http_json("GET", url)
    if data.get("status") != "success":
        raise RuntimeError(data.get("error", "prometheus query failed"))
    return data.get("data", {}).get("result", [])


def prom_scalar(prom_url: str, query: str, at: datetime | None = None) -> float | None:
    """Max over the returned series. None when the query returns nothing, which
    is an instrumentation gap and never a zero."""
    values = []
    for series in prom_query(prom_url, query, at=at):
        raw = series.get("value", [None, None])[1]
        if raw is not None:
            try:
                values.append(float(raw))
            except ValueError:
                pass
    return max(values) if values else None


def prom_query_range(prom_url: str, query: str, start: datetime, end: datetime,
                     step: str) -> list[dict]:
    """Raw `result` list from /api/v1/query_range — one entry per series, each
    with its labels under "metric" and its samples under "values"."""
    url = f"{prom_url}/api/v1/query_range?" + urllib.parse.urlencode({
        "query": query,
        "start": start.timestamp(),
        "end": end.timestamp(),
        "step": step,
    })
    data = shell.http_json("GET", url)
    if data.get("status") != "success":
        raise RuntimeError(data.get("error", "prometheus range query failed"))
    return data.get("data", {}).get("result", [])


def prom_targets_down(prom_url: str) -> list[str]:
    return [
        f'{r["metric"].get("job", "?")}/{r["metric"].get("instance", "?")}'
        for r in prom_query(prom_url, "up == 0")
    ]


def check_guards(prom_url: str, guards: list[dict],
                 at: datetime | None = None) -> list[str]:
    """Evaluated once, as of `at` (Prometheus's own "now" when not given).

    Pass the instant the load actually stopped, not the moment you got around
    to checking. Guards run after the window closes and after the export, which
    is minutes later; a rate-based guard with a [5m] lookback evaluated then is
    averaging its own lookback over dead air rather than over the load it is
    meant to validate, and quietly passes.

    A guard returning nothing fails: an empty result is a gap, not a pass. Use
    `or vector(0)` where a zero is honest."""
    failures = []
    for guard in guards:
        ref = guard["ref"]
        try:
            value = prom_scalar(prom_url, guard["query"], at=at)
        except RuntimeError as e:
            print(f"[{BAD}] guard {ref} — query failed: {e}")
            failures.append(ref)
            continue
        if value is None:
            print(f"[{BAD}] guard {ref} — NO DATA (a gap, not a zero)")
            failures.append(ref)
            continue
        low, high = guard.get("min"), guard.get("max")
        breached = ((low is not None and value < low)
                    or (high is not None and value > high))
        bound = " · ".join(f"{k} {v:g}" for k, v in (("min", low), ("max", high))
                           if v is not None)
        print(f"[{BAD if breached else OK}] guard {ref} = {value:g}  [{bound}]")
        if breached:
            failures.append(ref)
    return failures


@dataclass
class Export:
    """What landed on disk, and what didn't."""

    path: Path
    meta_path: Path
    series: int = 0
    points: int = 0
    empty: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """An empty ref is a gap, not a zero — the query returned no series at
        all, so there is nothing to say about that metric for this window."""
        return not self.empty


def export_range(prom_url: str, series: list[list[str]], window: Window, *,
                 out_dir: Path, run_id: str, step: str = "15s",
                 force: bool = False) -> Export:
    """Snapshot every `ref|promql` row over `window` into `<out_dir>/<run_id>.jsonl`,
    plus a `.meta.json` manifest.

    Metrics have retention; a window you failed to export is unrecoverable
    once it ages out, and unlike the run itself it cannot be repeated. So
    this writes every ref it can and reports the gaps rather than aborting
    on the first failure — a partial export still rescues most of the window.

    `series` is what refs.read_ref_file(path, 2) returns. One JSON object per
    line: {"metric": ref, "query": q, "result": [...]} — the shape jsonl.py
    reads back.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run_id}.jsonl"
    meta_path = out_dir / f"{run_id}.meta.json"
    if path.exists() and not force:
        die(f"{path} exists — pass force=True to overwrite (it holds a window "
            f"that cannot be re-measured, only re-exported)")

    start_s, end_s = window.rfc3339
    print(f"{ARROW} exporting {len(series)} ref(s) · {start_s} .. {end_s} · step {step}")

    export = Export(path=path, meta_path=meta_path)
    manifest = []
    with path.open("w") as out:
        for ref, query in series:
            try:
                result = prom_query_range(prom_url, query, window.start,
                                          window.end, step)
            except RuntimeError as e:
                print(f"[{BAD}] {ref} — {e}")
                export.empty.append(ref)
                result = []
            points = sum(len(s.get("values", [])) for s in result)
            if not result:
                if ref not in export.empty:
                    print(f"[{BAD}] {ref} — NO DATA")
                    export.empty.append(ref)
            else:
                print(f"[{OK}] {ref} — {len(result)} series, {points} points")
            export.series += len(result)
            export.points += points
            manifest.append({"ref": ref, "query": query,
                             "series": len(result), "points": points})
            out.write(json.dumps({"metric": ref, "query": query,
                                  "result": result}) + "\n")

    meta_path.write_text(json.dumps({
        "run": run_id,
        "exported_at": rfc3339(utcnow()),
        "prom_url": prom_url,
        "step": step,
        "window": window.to_dict(),
        "refs": manifest,
    }, indent=2) + "\n")

    if export.empty:
        print(f"{WARN} {len(export.empty)} ref(s) came back empty: "
              f"{', '.join(export.empty)}")
    print(f"[{OK}] {path} · {export.series} series · {export.points} points")
    return export

"""Everything a point does once its window has closed, the same for every
profile and safe to run again on the record alone: the window exported, the
guards read as of the instant the plan names, the register's refs worked out,
the journal block written, and the exit code that says what happened."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import derive, price_check, prometheus, reporting
from .clock import hms, parse_instant
from .constants import BAD, EXIT_EXPORT_GAP, EXIT_TIMEOUT, OK, WARN
from .execution_config import run_guards
from .launch import Load
from .point import Point, ceilings_reached
from .preflight import Preflight
from .register import Register, series_rows
from .watch import Watched
from .window import Window


def close_point(point: Point, pre: Preflight, watched: Watched, load: Load,
                observations: dict, doubts: list[str]) -> int:
    """Writes the record the moment the window is known — a run that dies
    exporting still leaves what `report-kit point finish` needs — then
    finishes it."""
    if watched.window is None:
        print(f"{BAD} the window never closed within "
              f"{hms(point.env.max_wait_seconds)} — nothing exported")
        return EXIT_TIMEOUT
    record = point_record(point, pre, watched, load, observations, doubts)
    if record["observations"]["ceilings_reached"]:
        print(f"{WARN} max_replicas reached: "
              f"{', '.join(record['observations']['ceilings_reached'])} — this "
              f"point measures that limit, not the system")
    path = reporting.write_record(point.out_dir, point.run, record)
    print()
    print(f"[{OK}] window {watched.window}")
    return finish_point(path, point.env.prom_url, point.register, force=point.args.force)


def point_record(point: Point, pre: Preflight, watched: Watched, load: Load,
                 observations: dict, doubts: list[str]) -> dict:
    events = {"load_started": load.started.timestamp(),
              "load_finished": load.finished.timestamp() if load.finished else None,
              "window_closed": watched.window.end.timestamp(), **watched.events}
    plan = point.plan
    return {
        "run": point.run,
        "profile": point.profile,
        "settings": point.settings,
        "window": watched.window.to_dict(),
        "load": {"exit": load.exit_code,
                 "window": load.window.to_dict() if load.window else None},
        "events": events,
        "observations": {"peaks": watched.peaks,
                         "ceilings_reached": ceilings_reached(point, watched.peaks),
                         **observations},
        "doubts": doubts,
        "plan": {"load": plan.load, "hold_seconds": plan.hold_seconds,
                 "step": plan.step, "guards_at": plan.guards_at},
        "queries": dict(series_rows(point.register)),
        "guards": run_guards(point.execution, point.settings),
        "price_check": price_plan(point),
        **pre.facts,
    }


def price_plan(point: Point) -> dict | None:
    match = point.execution.prices_match_aws
    return price_check.plan_of(match and match.within,
                               (metric.promql for metric in point.register.exported),
                               point.env.get("eks_cluster"))


def finish_point(record_path: Path, prom_url: str, register: Register, *,
                 force: bool = False) -> int:
    """Export, guards, the register's refs, the journal block, the verdict.
    Everything it needs is in the record, so it runs again on the record
    alone — after an export that failed, or under a newer kit."""
    record_path = Path(record_path)
    record = json.loads(record_path.read_text())
    plan = record.get("plan") or {}
    export = prometheus.export_range(
        prom_url, list((record.get("queries") or {}).items()), window_of(record),
        out_dir=record_path.parent, run_id=record["run"],
        step=plan.get("step", "15s"), force=force)
    print()
    guarded = prometheus.evaluate_guards(prom_url, record.get("guards") or [],
                                         at=guard_instant(record))
    record.update(guard_failures=guarded.failures, guard_values=guarded.values,
                  export={"path": str(export.path), "series": export.series,
                          "points": export.points, "empty_refs": export.empty},
                  prices=prices_checked(prom_url, record))
    markdown = journal_block(record, worked_out(register, record_path))
    path = reporting.write_point(record_path.parent, record["run"], markdown, record)
    print()
    print(f"[{OK}] {path}")
    return verdict(record, record_path)


def prices_checked(prom_url: str, record: dict) -> dict | None:
    """None when the execution does not ask for the check — a record from
    before it, or one whose execution.yaml has no prices_match_aws."""
    plan = record.get("price_check")
    if not plan:
        return None
    print()
    check = price_check.check_prices(prom_url, window_of(record), plan)
    price_check.print_check(check)
    return price_check.recorded(check)


def price_doubts(record: dict) -> list[str]:
    return (record.get("prices") or {}).get("doubts") or []


def instant(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, timezone.utc)


def window_of(record: dict) -> Window:
    """At full precision from `events` when the runner wrote them; from the
    window's RFC 3339 ends, to the second, for a record from before."""
    events = record.get("events") or {}
    if events.get("load_started") and events.get("window_closed"):
        return Window(instant(events["load_started"]), instant(events["window_closed"]))
    return Window(parse_instant(record["window"]["start"]),
                  parse_instant(record["window"]["end"]))


def guard_instant(record: dict) -> datetime:
    """As of the load's end or the window's, as the plan says — never now:
    minutes pass between the two, and a rate guard read now averages its
    lookback over dead air."""
    events = record.get("events") or {}
    wanted = (record.get("plan") or {}).get("guards_at", "load_end")
    if wanted == "load_end" and events.get("load_finished"):
        return instant(events["load_finished"])
    if wanted == "load_end" and (record.get("generator_window") or {}).get("end"):
        return parse_instant(record["generator_window"]["end"])
    if wanted == "load_end":
        print(f"{WARN} guards_at is load_end, but the load was still running when "
              f"the window closed — guards read as of the window's end")
    return window_of(record).end


def worked_out(register: Register, record_path: Path) -> list[tuple[str, str, str]]:
    """Every ref the run's data holds: (ref, what it measures, its number or
    why there is none)."""
    rows = []
    for metric in register.metrics:
        if not metric.derived_from_data:
            continue
        try:
            value = derive.derive(register, metric.ref, record_path, record_path.name)
            shown = f"{value:.6g}"
        except derive.DeriveError as exc:
            shown = f"gap — {exc}"
        rows.append((metric.ref, metric.what, shown))
    return rows


def journal_block(record: dict, refs: list[tuple[str, str, str]]) -> str:
    """What the point's .point.md holds: the run as one table, then what its
    data gives each ref of the register."""
    start, end = record["window"]["start"], record["window"]["end"]
    rows = [("run", f"`{record['run']}`"), ("profile", str(record.get("profile", "")))]
    rows += [(name, str(value)) for name, value in (record.get("settings") or {}).items()]
    rows += [("window", f"`{start}` .. `{end}` ({hms(record['window']['seconds'])})"),
             ("commit", f"`{str(record.get('commit', '?'))[:12]}`"
                        f"{' (dirty)' if record.get('dirty') else ''}"),
             ("load exit", str((record.get("load") or {}).get("exit"))),
             ("guards", ", ".join(record["guard_failures"]) or "clean"),
             ("series exported", f"{record['export']['series']} "
                                 f"({record['export']['points']} points)")]
    if record.get("prices") is not None:
        rows += [("prices", prices_summary(record["prices"]))]
    rows += [(name, listed(value)) for name, value in
             (record.get("observations") or {}).items()]
    rows += [("doubts", "; ".join(record.get("doubts") or []) or "none")]
    lines = reporting.md_table(rows)
    if refs:
        lines += ["", "| Ref | What it measures | This run |", "| :--- | :--- | ---: |"]
        lines += [f"| {ref} | {what} | {shown} |" for ref, what, shown in refs]
    return "\n".join(lines)


def prices_summary(prices: dict) -> str:
    doubted = len(prices["doubts"])
    return (f"{len(prices['checked'])} checked against AWS within "
            f"{prices['within']:.1%}, " + (f"{doubted} in doubt" if doubted else "clean"))


def listed(value: object) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}={item:g}" if isinstance(item, float) else f"{key}={item}"
                         for key, item in sorted(value.items())) or "none"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "none"
    return str(value)


def verdict(record: dict, record_path: Path) -> int:
    empty = record["export"]["empty_refs"]
    if empty:
        print(f"{WARN} export gaps: {', '.join(empty)} — the window is recorded; "
              f"run report-kit point finish {record_path} --force before "
              f"retention drops it")
        return EXIT_EXPORT_GAP
    return reporting.report_validity([*(record.get("doubts") or []), *price_doubts(record)],
                                     record["guard_failures"])

"""One point's inputs, opened the same way by every runner: its command line,
built from the settings `execution.yaml` declares; the three YAML files; the
port-forwards; the image freeze; and the preflight every point shares."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import cluster, opencost, prometheus, reporting
from .constants import EXIT_CLEAN, EXIT_PREFLIGHT, OK, die
from .env import Env
from .execution_config import (EXECUTION, Execution, ExecutionError, PointPlan,
                               read_execution, run_guards)
from .portforward import PortForwards, forward_spec
from .preflight import Preflight
from .register import REGISTER, Register, RegisterError, read_register

COMMON_FLAGS = frozenset({"run", "env", "metrics", "execution", "out_dir",
                          "freeze_file", "preflight_only", "set_freeze",
                          "no_port_forward", "force"})


@dataclass(frozen=True)
class Point:
    here: Path
    args: argparse.Namespace
    env: Env
    register: Register
    execution: Execution
    plan: PointPlan
    profile: str

    @property
    def run(self) -> str:
        return self.args.run

    @property
    def out_dir(self) -> Path:
        return self.args.out_dir or self.here / "data"

    @property
    def freeze_file(self) -> Path:
        return self.args.freeze_file or self.here / "image-freeze.json"

    @property
    def settings(self) -> dict[str, str | None]:
        return {setting.name: getattr(self.args, setting.name)
                for setting in self.plan.settings}


def open_point(here: Path, profile: str, defaults: PointPlan, description: str,
               argv: list[str] | None = None,
               flags: Callable[[argparse.ArgumentParser], None] | None = None) -> Point:
    """`defaults` is the profile's plan; `execution.yaml` replaces what it names.
    `flags` adds a runner's own options to the command line."""
    located = locations().parse_known_args(argv)[0]
    register, execution = definitions(located.metrics or here.parent / REGISTER,
                                      located.execution or here.parent / EXECUTION)
    plan = execution.plan(defaults)
    parser = point_parser(plan, description)
    if flags:
        flags(parser)
    args = parser.parse_args(argv)
    return Point(here, args, Env(args.env or here / "env.yaml"), register,
                 execution, plan, profile)


def locations() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--execution", type=Path)
    return parser


def definitions(metrics: Path, execution: Path) -> tuple[Register, Execution]:
    try:
        register = read_register(metrics)
        return register, read_execution(execution, register)
    except (RegisterError, ExecutionError) as exc:
        die(str(exc))


def point_parser(plan: PointPlan, description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", help="point id; names every file the point writes")
    for setting in plan.settings:
        if setting.name in COMMON_FLAGS:
            die(f"setting {setting.name!r} in {EXECUTION} is one of the runner's own flags")
        p.add_argument(f"--{setting.name.replace('_', '-')}", dest=setting.name,
                       default=setting.default,
                       help=f"default {setting.default}" if setting.default
                       else "required for a measured point")
    p.add_argument("--env", type=Path, help="env.yaml (default: next to the runner)")
    p.add_argument("--metrics", type=Path,
                   help=f"{REGISTER} (default: the execution's, above the runner)")
    p.add_argument("--execution", type=Path,
                   help=f"{EXECUTION} (default: the execution's, above the runner)")
    p.add_argument("--out-dir", type=Path, help="where the point's files land")
    p.add_argument("--freeze-file", type=Path, help="image-freeze.json")
    p.add_argument("--preflight-only", action="store_true")
    p.add_argument("--set-freeze", action="store_true",
                   help="record the current images as the freeze and exit")
    p.add_argument("--no-port-forward", action="store_true")
    p.add_argument("--force", action="store_true",
                   help="overwrite an existing export for this run id")
    return p


def require_settings(point: Point) -> list[dict]:
    """The guards, filled; dies before any load runs if a setting is missing
    or a guard names one this point does not have."""
    missing = [f"--{name.replace('_', '-')}" for name, value in point.settings.items()
               if value is None]
    if not point.run or missing:
        die(f"{' and '.join(['--run', *missing])} are required for a measured point")
    try:
        return run_guards(point.execution, point.settings)
    except ExecutionError as exc:
        die(str(exc))


def port_forwards(point: Point, *names: str) -> PortForwards:
    return PortForwards([forward_spec(point.env, name) for name in names],
                        enabled=not point.args.no_port_forward)


def record_freeze(point: Point) -> int:
    if not point.plan.freeze:
        die(f"{point.execution.path} names nothing under point.freeze to freeze")
    images = reporting.frozen_images(point.env, list(point.plan.freeze))
    point.freeze_file.parent.mkdir(parents=True, exist_ok=True)
    point.freeze_file.write_text(json.dumps(images, indent=2, sort_keys=True) + "\n")
    print(f"[{OK}] freeze written to {point.freeze_file}")
    return EXIT_CLEAN


def preflight(point: Point, more: Callable[[Preflight], None] | None = None) -> Preflight:
    """The checks every point shares; `more` adds the profile's own."""
    pre = Preflight("preflight")
    for target in point.execution.window_closes_when_back_to_idle:
        try:
            count = replicas(point, target.deployment)
        except RuntimeError as exc:
            pre.fail(f"{target.deployment} replicas unreadable", str(exc))
            continue
        pre.check(f"{target.deployment} at idle", count <= target.idle_replicas,
                  f"{count} replica(s), idle {target.idle_replicas}")
    if more:
        more(pre)
    check_price_inputs(point, pre)
    down = prometheus.prom_targets_down(point.env.prom_url)
    pre.check("prometheus targets up", not down, ", ".join(down[:5]))
    check_images(point, pre)
    pre.record(**reporting.git_facts())
    return pre


def check_price_inputs(point: Point, pre: Preflight) -> None:
    """The control-plane fee is the one price checked against a named cluster;
    finding out it is unnamed after the window closed costs the point."""
    if point.execution.prices_match_aws is None:
        return
    lines = opencost.lines_read(metric.promql for metric in point.register.exported)
    if opencost.CONTROL_PLANE in lines:
        pre.check("eks_cluster in env.yaml", bool(point.env.get("eks_cluster")),
                  "the control-plane fee OpenCost publishes is checked against "
                  "that cluster's")


def check_images(point: Point, pre: Preflight) -> None:
    if not point.plan.freeze:
        pre.warn("no image freeze", f"{EXECUTION} names nothing under point.freeze, "
                                    f"so the sweep cannot show it measured one artifact")
        return
    images = reporting.frozen_images(point.env, list(point.plan.freeze))
    for problem in reporting.check_freeze(point.freeze_file, images):
        pre.fail("image freeze", problem)
    pre.record(images=images)


def verdict(pre: Preflight) -> int:
    return EXIT_CLEAN if pre.finish(exit_on_fail=False) else EXIT_PREFLIGHT


def replicas(point: Point, deployment: str) -> int:
    return cluster.deployment_replicas(point.env.namespace_for(deployment), deployment)


def tier_replicas(point: Point) -> dict[str, int]:
    return {target.deployment: replicas(point, target.deployment)
            for target in point.execution.window_closes_when_back_to_idle}


def tiers_at_rest(point: Point, current: dict[str, int]) -> bool:
    return all(current[target.deployment] <= target.idle_replicas
               for target in point.execution.window_closes_when_back_to_idle)


def ceilings_reached(point: Point, peaks: dict[str, float]) -> list[str]:
    """Deployments that reached max_replicas: the point measured that limit."""
    return [target.deployment
            for target in point.execution.window_closes_when_back_to_idle
            if target.max_replicas
            and peaks.get(f"tiers.{target.deployment}", 0) >= target.max_replicas]

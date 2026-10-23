"""The load a point applies, as env.yaml names it: one process, its command
filled from the run's settings, run to completion or in the background."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .constants import ARROW, BAD, OK, die
from .proc import Background, run_logged
from .text import fill
from .window import Window

if TYPE_CHECKING:
    from .point import Point


@dataclass(frozen=True)
class Load:
    """`finished` and `exit_code` are None for a load still running when the
    window closed."""

    started: datetime
    finished: datetime | None
    exit_code: int | None
    log: Path

    @property
    def window(self) -> Window | None:
        return None if self.finished is None else Window(self.started, self.finished)


def load_command(point: "Point", key: str) -> tuple[list[str], dict[str, str], Path]:
    """`<key>.command` and `<key>.env` from env.yaml, with {run} {log} {summary}
    and every setting filled in."""
    log = point.out_dir / f"{point.run}.{key}.log"
    values = {"run": point.run, "log": str(log),
              "summary": str(point.out_dir / f"{point.run}.summary.json"),
              **point.settings}
    try:
        command = [fill(str(part), values) for part in point.env.need(f"{key}.command")]
        extra = {name: fill(str(value), values)
                 for name, value in (point.env.get(f"{key}.env") or {}).items()}
    except KeyError as exc:
        die(f"{key} names {{{exc.args[0]}}}, which this point does not fill — it "
            f"fills {', '.join(sorted(values))}")
    return command, extra, log


def run_load(point: "Point", key: str = "generator") -> Load:
    """Runs to completion: the load is exactly this process's lifetime."""
    command, extra, log = load_command(point, key)
    print()
    print(f"{ARROW} {key} · {' '.join(command)}")
    # cwd is the runner's directory: a command naming a script beside it must
    # not depend on where the operator stood when they invoked the runner.
    done = run_logged(command, log, env_extra=extra, cwd=point.here)
    print(f"[{OK if done.ok else BAD}] {key} exit {done.returncode} · "
          f"{done.window.hms} · {log}")
    return Load(done.window.start, done.window.end, done.returncode, log)


def start_load(point: "Point", key: str = "producer") -> Background:
    """Runs while the window is watched; use as a context manager."""
    command, extra, log = load_command(point, key)
    print()
    print(f"{ARROW} {key} (background) · {' '.join(command)}")
    return Background(command, log, env_extra=extra, cwd=point.here)


def load_of(producer: Background) -> Load:
    """What a background load did by the time the window closed."""
    code = producer.poll()
    if code not in (0, None):
        print(f"{BAD} {producer.log_path.name} exited {code} — tail:")
        for line in producer.tail():
            print(f"         {line}")
    return Load(producer.started_at, producer.finished_at, code, producer.log_path)

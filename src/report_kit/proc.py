from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .clock import utcnow
from .window import Window


@dataclass(frozen=True)
class Completed:
    returncode: int
    window: Window
    log_path: Path

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_logged(cmd: list[str], log_path: Path, *, env_extra: dict | None = None,
               cwd: Path | None = None, timeout: float | None = None) -> Completed:
    """Run to completion with output captured to a file, timing the run.

    For load generators (k6, vegeta, a producer script) where you have
    nothing to do until it finishes: the window is exactly this process's
    lifetime, and the timestamps come from the run rather than from a
    variable someone set two functions earlier.

    Output goes to a file, not a pipe: a generator can emit far more than a
    pipe buffer holds, and a full pipe with nobody reading it deadlocks."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **(env_extra or {})}
    start = utcnow()
    with log_path.open("w") as log:
        proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,
                              env=env, cwd=str(cwd) if cwd else None,
                              timeout=timeout)
    return Completed(proc.returncode, Window(start, utcnow()), log_path)


class Background:
    """A child process that runs *while* you watch something else.

    The async/jobs profile needs this: the producer fills the queue and the
    watch loop observes the system draining it at the same time. Waiting for
    the producer first would measure a queue that was already full, which is
    a different experiment.

    Use as a context manager. On exit a still-running child is killed by
    process group (`start_new_session=True` above makes that safe), so an
    exception in the watch loop can't leave a producer writing into the next
    point's window."""

    def __init__(self, cmd: list[str], log_path: Path, *,
                 env_extra: dict | None = None, cwd: Path | None = None):
        self.cmd = cmd
        self.log_path = Path(log_path)
        self.env_extra = env_extra or {}
        self.cwd = cwd
        self.proc: subprocess.Popen | None = None
        self.started_at = None
        self.finished_at = None

    def start(self) -> "Background":
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log = self.log_path.open("w")
        self.started_at = utcnow()
        self.proc = subprocess.Popen(
            self.cmd, stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, **self.env_extra},
            cwd=str(self.cwd) if self.cwd else None,
            start_new_session=True,
        )
        log.close()  # the child holds its own fd now
        return self

    def __enter__(self) -> "Background":
        return self.start() if self.proc is None else self

    def poll(self) -> int | None:
        """Exit code, or None while it's still running. Never blocks."""
        if self.proc is None:
            return None
        code = self.proc.poll()
        if code is not None and self.finished_at is None:
            self.finished_at = utcnow()
        return code

    def wait(self, timeout: float | None = None) -> int:
        if self.proc is None:
            raise RuntimeError("not started")
        code = self.proc.wait(timeout=timeout)
        self.finished_at = self.finished_at or utcnow()
        return code

    @property
    def running(self) -> bool:
        return self.proc is not None and self.poll() is None

    @property
    def window(self) -> Window | None:
        """Only once it has finished — a window with no end isn't a window."""
        if self.started_at is None or self.finished_at is None:
            return None
        return Window(self.started_at, self.finished_at)

    def tail(self, lines: int = 5) -> list[str]:
        try:
            return self.log_path.read_text().strip().splitlines()[-lines:]
        except OSError:
            return []

    def kill(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
        except Exception:
            self.proc.terminate()
        self.finished_at = self.finished_at or utcnow()

    def __exit__(self, *_):
        self.kill()
        return False

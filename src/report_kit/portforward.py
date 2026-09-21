from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from typing import TYPE_CHECKING

from .constants import ARROW, die

if TYPE_CHECKING:                    # a type hint shouldn't require PyYAML
    from .env import Env


class PortForwards:
    """Opens what the runner asks for. Torn down on exit, including on a raise.

    `kubectl port-forward` has no reconnect logic of its own and is known to
    drop silently on a long-lived tunnel (idle timeout to the API server, a
    network blip, the target pod rescheduling) — a real risk over a run that
    can watch for the better part of an hour. `ensure_alive()` is the fix:
    call it periodically (the watch loop) and right before anything that
    depends on the tunnel (the R21 read, the Prometheus export) so a dead
    forward gets relaunched before it causes a gap instead of after."""

    def __init__(self, targets: list[dict], enabled: bool = True):
        self.enabled = enabled
        self.targets = [t for t in targets if t]
        self.procs: list[subprocess.Popen] = []
        self.logs: list[Path] = []

    def _launch(self, spec: dict) -> tuple[subprocess.Popen, Path]:
        log_path = Path(tempfile.gettempdir()) / (
            f"port-forward-{spec['namespace']}-"
            f"{spec['target'].replace('/', '_')}.log")
        log_file = log_path.open("w")
        proc = subprocess.Popen(
            ["kubectl", "-n", spec["namespace"], "port-forward",
             spec["target"], spec["mapping"]],
            stdout=subprocess.DEVNULL, stderr=log_file,
            start_new_session=True,
        )
        log_file.close()  # child inherited the fd; this process doesn't need it open
        return proc, log_path

    def __enter__(self):
        if not self.enabled or not self.targets:
            return self
        for spec in self.targets:
            print(f"{ARROW} port-forward : {spec['namespace']}/{spec['target']} "
                  f"{spec['mapping']}")
            proc, log_path = self._launch(spec)
            self.procs.append(proc)
            self.logs.append(log_path)
        time.sleep(4)
        for proc, spec in zip(self.procs, self.targets):
            if proc.poll() is not None:
                die(f"a port-forward died immediately ({spec['namespace']}/"
                    f"{spec['target']}) — check the service names in env.yaml, "
                    f"its log, or pass --no-port-forward and open them yourself")
        return self

    def ensure_alive(self) -> list[str]:
        """Relaunch any forward that died. Returns one message per restart,
        empty when everything is still up — call and print the result rather
        than assuming silence means nothing happened."""
        if not self.enabled:
            return []
        notices = []
        for i, proc in enumerate(self.procs):
            if proc.poll() is None:
                continue
            spec = self.targets[i]
            tail = ""
            try:
                tail = self.logs[i].read_text().strip().splitlines()[-1:]
                tail = f" — {tail[0]}" if tail else ""
            except OSError:
                pass
            notices.append(
                f"port-forward {spec['namespace']}/{spec['target']} died "
                f"(exit {proc.returncode}){tail} — relaunching")
            new_proc, new_log = self._launch(spec)
            time.sleep(2)
            if new_proc.poll() is not None:
                notices.append(
                    f"port-forward {spec['namespace']}/{spec['target']} "
                    f"failed to relaunch — see {new_log}")
            self.procs[i] = new_proc
            self.logs[i] = new_log
        return notices

    def __exit__(self, *_):
        for proc in self.procs:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                proc.terminate()
        return False


def forward_spec(env: "Env", prefix: str) -> dict | None:
    """Build a port-forward entry from an env block, or None when it names no
    service — a URL already reachable needs no tunnel."""
    service = env.get(f"{prefix}.service")
    if not service:
        return None
    return {"namespace": env.get(f"{prefix}.namespace", env.namespace),
            "target": service,
            "mapping": env.get(f"{prefix}.mapping", "")}

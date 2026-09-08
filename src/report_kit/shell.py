from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request

from .constants import die


def sh(cmd: list[str], timeout: int = 60) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        die(f"command not found: {cmd[0]}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"timeout: {' '.join(cmd[:4])}...") from None
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:300] or f"exit {proc.returncode}")
    return proc.stdout


def sh_json(cmd: list[str], timeout: int = 60) -> dict:
    out = sh(cmd, timeout=timeout)
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise RuntimeError(f"not JSON from {cmd[0]}") from None


def http_json(method: str, url: str, body: dict | None = None,
              timeout: int = 30) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"cannot reach {url}: {e.reason}") from None
    return json.loads(raw) if raw.strip() else {}

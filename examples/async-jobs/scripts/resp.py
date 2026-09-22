"""resp.py — the ten lines of the Redis wire protocol this example needs.

Shared by the host-side scripts (`point.py`, `produce.py`) and, through the
`jobs-src` ConfigMap that `up.sh` builds from this directory, by the pods
inside the cluster. One file, so the queue is spoken the same way on both
sides.

Not in `report_kit`, on purpose. It is the same call as `read_k6_summary` in
`../../simple-api/scripts/point.py`: the shape of one queue is the example's
business, and the kit stays queue-agnostic. If a project needs Redis for real
it should install `redis-py`, not copy this.
"""

from __future__ import annotations

import socket


class Redis:
    """One connection, synchronous, no pooling. Enough for a producer and a
    depth probe; deliberately not enough to be mistaken for a client library."""

    def __init__(self, host: str = "localhost", port: int = 6379,
                 timeout: float = 10.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.buf = self.sock.makefile("rb")

    @classmethod
    def from_address(cls, address: str, **kwargs) -> "Redis":
        """'host:port', as env.yaml writes it."""
        host, _, port = address.partition(":")
        return cls(host or "localhost", int(port or 6379), **kwargs)

    def call(self, *args):
        out = b"*%d\r\n" % len(args)
        for arg in args:
            raw = arg if isinstance(arg, bytes) else str(arg).encode()
            out += b"$%d\r\n%s\r\n" % (len(raw), raw)
        self.sock.sendall(out)
        return self._read()

    def _read(self):
        line = self.buf.readline()
        if not line:
            raise RuntimeError("redis closed the connection")
        kind, body = line[:1], line[1:-2]
        if kind == b"+":
            return body.decode()
        if kind == b"-":
            raise RuntimeError(body.decode())
        if kind == b":":
            return int(body)
        if kind == b"$":
            if body == b"-1":
                return None
            data = self.buf.read(int(body) + 2)
            return data[:-2]
        if kind == b"*":
            if body == b"-1":
                return None
            return [self._read() for _ in range(int(body))]
        raise RuntimeError(f"unexpected reply {line!r}")

    def close(self) -> None:
        try:
            self.buf.close()
            self.sock.close()
        except OSError:
            pass

    def __enter__(self) -> "Redis":
        return self

    def __exit__(self, *_):
        self.close()
        return False

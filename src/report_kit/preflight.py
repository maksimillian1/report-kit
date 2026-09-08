from __future__ import annotations

import sys

from .constants import ARROW, BAD, EXIT_PREFLIGHT, OK, WARN


class Preflight:
    """A checklist that collects every failure before deciding to stop.

    Dying on the first failed check makes you rediscover the state of the
    system one run per problem: fix the queue, rerun, learn the pool isn't
    at zero, fix that, rerun, learn the image freeze moved. All of those are
    knowable in one pass, so gather them all and report once.

    Checks print as they happen (a preflight that goes quiet for 40s looks
    hung); the verdict prints at finish()."""

    def __init__(self, title: str = "preflight"):
        self.title = title
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.facts: dict = {}
        print(f"{ARROW} {title}")

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        """Record a pass/fail. Returns `ok`, so it can also be used inline."""
        tail = f" — {detail}" if detail else ""
        print(f"[{OK if ok else BAD}] {label}{tail}")
        if not ok:
            self.failures.append(f"{label}{tail}")
        return ok

    def fail(self, label: str, detail: str = "") -> None:
        self.check(label, False, detail)

    def warn(self, label: str, detail: str = "") -> None:
        """Noted in the record, never blocks the run."""
        tail = f" — {detail}" if detail else ""
        print(f"{WARN} {label}{tail}")
        self.warnings.append(f"{label}{tail}")

    def record(self, **facts) -> None:
        """Facts worth carrying into the point record (commit, image digests,
        starting counts) — gathered during preflight because that's when the
        system is in its known state."""
        self.facts.update(facts)

    @property
    def ok(self) -> bool:
        return not self.failures

    def finish(self, *, exit_on_fail: bool = True) -> bool:
        if self.ok:
            return True
        print()
        print(f"{BAD} {self.title} failed on {len(self.failures)} check(s):")
        for failure in self.failures:
            print(f"         · {failure}")
        if exit_on_fail:
            sys.exit(EXIT_PREFLIGHT)
        return False
